"""
audio_engine.py
WASAPI loopback 擷取系統音訊，套用 normalizer，輸出固定音量到目標裝置。
"""

import threading
import queue
import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None


def db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


def linear_to_db(linear: float) -> float:
    if linear <= 0:
        return -96.0
    return 20.0 * np.log10(max(linear, 1e-10))


class AudioEngine:
    CHUNK = 1024
    FORMAT = None  # set in __init__
    CHANNELS = 2
    RATE = 48000

    def __init__(self):
        self._pa = None
        self._stream_in = None
        self._stream_out = None
        self._running = False
        self._thread = None

        # target output level, default -10 dBFS
        self._target_db = -10.0
        self._target_linear = db_to_linear(self._target_db)

        # bypass flag
        self._bypass = False

        # meter data queue: (in_db, out_db, gr_db)
        self.meter_queue: queue.Queue = queue.Queue(maxsize=20)

        # selected device indices
        self.loopback_device_index = None
        self.output_device_index = None

        if pyaudio:
            self.FORMAT = pyaudio.paFloat32
            self._pa = pyaudio.PyAudio()

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------

    def get_loopback_devices(self) -> list[dict]:
        """回傳所有 WASAPI loopback 裝置清單。"""
        if not self._pa:
            return []
        devices = []
        try:
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            return []
        for i in range(self._pa.get_device_count()):
            dev = self._pa.get_device_info_by_index(i)
            if dev.get("hostApi") == wasapi_info["index"] and dev.get("maxInputChannels") > 0:
                # loopback devices have "loopback" in name or isLoopbackDevice flag
                if dev.get("isLoopbackDevice", False):
                    devices.append({"index": i, "name": dev["name"]})
        return devices

    def get_output_devices(self) -> list[dict]:
        """回傳所有 WASAPI 輸出裝置清單（包含 VB-Cable）。"""
        if not self._pa:
            return []
        devices = []
        try:
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            wasapi_index = wasapi_info["index"]
        except OSError:
            return []

        for i in range(self._pa.get_device_count()):
            dev = self._pa.get_device_info_by_index(i)
            # Bug 3 fix: 只列 WASAPI 裝置，避免與 WASAPI loopback 輸入混用造成開流失敗
            if dev.get("hostApi") == wasapi_index and dev.get("maxOutputChannels") > 0:
                tag = ""
                if "VB-Audio" in dev["name"] or "CABLE" in dev["name"].upper():
                    tag = " [VB-Cable]"
                devices.append({"index": i, "name": dev["name"] + tag})
        return devices

    def has_vbcable(self) -> bool:
        for d in self.get_output_devices():
            name = d["name"].upper()
            if "VB-AUDIO" in name or "CABLE INPUT" in name:
                return True
        return False

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def set_threshold_db(self, db: float):
        self._target_db = db
        self._target_linear = db_to_linear(db)

    def get_threshold_db(self) -> float:
        return self._target_db

    def set_bypass(self, bypass: bool):
        self._bypass = bypass

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self, loopback_index: int, output_index: int):
        if self._running:
            return
        if not self._pa:
            raise RuntimeError("pyaudiowpatch 未安裝")

        self.loopback_device_index = loopback_index
        self.output_device_index = output_index
        # Bug 2 fix: 用 Event 等待 thread 確認串流開啟成功或失敗
        self._start_event = threading.Event()
        self._start_error: str | None = None
        self._running = True
        self._thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._thread.start()
        # 最多等 3 秒讓 thread 完成 pa.open()
        self._start_event.wait(timeout=3)
        if self._start_error is not None:
            self._running = False
            raise RuntimeError(self._start_error)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    # ------------------------------------------------------------------
    # Audio loop (runs in background thread)
    # ------------------------------------------------------------------

    def _audio_loop(self):
        pa = self._pa

        loopback_dev = pa.get_device_info_by_index(self.loopback_device_index)
        output_dev = pa.get_device_info_by_index(self.output_device_index)

        channels = min(int(loopback_dev.get("maxInputChannels", 2)), 2)

        # 各自用裝置 native rate，rate 不同時做 resample
        in_rate  = int(loopback_dev.get("defaultSampleRate", self.RATE))
        out_rate = int(output_dev.get("defaultSampleRate", self.RATE))

        # 增益平滑係數基於輸入 rate
        attack_coeff  = 1.0 - np.exp(-self.CHUNK / (in_rate * 0.050))
        release_coeff = 1.0 - np.exp(-self.CHUNK / (in_rate * 0.300))
        smooth_gain = 1.0

        try:
            stream_in = pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=in_rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=self.CHUNK,
            )
            stream_out = pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=out_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.CHUNK,
            )
        except Exception as e:
            self._running = False
            self._start_error = str(e)
            self._start_event.set()  # Bug 2 fix: 通知 start() 開流失敗
            try:
                self.meter_queue.put_nowait(("error", str(e)))
            except queue.Full:
                pass
            return

        # Bug 2 fix: 通知 start() 開流成功
        self._start_event.set()

        while self._running:
            try:
                raw = stream_in.read(self.CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.float32).copy()

                in_rms = float(np.sqrt(np.mean(samples ** 2)))
                in_db = linear_to_db(in_rms)

                if not self._bypass:
                    if in_rms > 1e-6:
                        target_gain = self._target_linear / in_rms
                        # 最多放大 +12dB，降低爆音風險
                        target_gain = min(target_gain, db_to_linear(12.0))
                    else:
                        target_gain = smooth_gain  # 靜音時維持現有增益，不跳變

                    # 增益平滑：上升用 attack，下降用 release
                    if target_gain < smooth_gain:
                        smooth_gain = smooth_gain + attack_coeff * (target_gain - smooth_gain)
                    else:
                        smooth_gain = smooth_gain + release_coeff * (target_gain - smooth_gain)

                    normalized = samples * smooth_gain

                    # soft knee limiter：用 tanh 替代 hard clip，避免截斷失真
                    # tanh(x) 在 |x| < 0.9 幾乎線性，超過才平滑壓縮至 [-1, 1]
                    clipped = np.tanh(normalized)
                else:
                    clipped = samples

                out_rms = float(np.sqrt(np.mean(clipped ** 2)))
                out_db = linear_to_db(out_rms)
                gr_db = out_db - in_db  # gain reduction (negative = reducing)

                # rate 不同時做線性 resample（48000→44100 等）
                if in_rate != out_rate:
                    total_in  = len(clipped)
                    # clipped 是 interleaved，共 total_in/channels 個 frame
                    n_frames_in  = total_in // channels
                    n_frames_out = int(round(n_frames_in * out_rate / in_rate))
                    # reshape 成 (frames, channels)，每聲道獨立插值，再 flatten
                    arr = clipped.reshape(n_frames_in, channels)
                    x_in  = np.linspace(0, 1, n_frames_in,  endpoint=False)
                    x_out = np.linspace(0, 1, n_frames_out, endpoint=False)
                    resampled = np.empty((n_frames_out, channels), dtype=np.float32)
                    for ch in range(channels):
                        resampled[:, ch] = np.interp(x_out, x_in, arr[:, ch])
                    clipped = resampled.flatten()

                stream_out.write(clipped.tobytes())

                try:
                    self.meter_queue.put_nowait((in_db, out_db, gr_db))
                except queue.Full:
                    pass
            except Exception:
                break

        stream_in.stop_stream()
        stream_in.close()
        stream_out.stop_stream()
        stream_out.close()

    def close(self):
        self.stop()
        if self._pa:
            self._pa.terminate()
