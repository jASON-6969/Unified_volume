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
        """回傳所有輸出裝置清單（包含 VB-Cable）。"""
        if not self._pa:
            return []
        devices = []
        try:
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            wasapi_index = wasapi_info["index"]
        except OSError:
            wasapi_index = -1

        for i in range(self._pa.get_device_count()):
            dev = self._pa.get_device_info_by_index(i)
            if dev.get("maxOutputChannels") > 0:
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
        self._running = True
        self._thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._thread.start()

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
        rate = int(loopback_dev.get("defaultSampleRate", self.RATE))
        channels = min(int(loopback_dev.get("maxInputChannels", 2)), 2)

        try:
            stream_in = pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=self.loopback_device_index,
                frames_per_buffer=self.CHUNK,
            )
            stream_out = pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.CHUNK,
            )
        except Exception as e:
            self._running = False
            # push error signal via meter queue
            try:
                self.meter_queue.put_nowait(("error", str(e)))
            except queue.Full:
                pass
            return

        while self._running:
            try:
                raw = stream_in.read(self.CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.float32).copy()

                in_rms = float(np.sqrt(np.mean(samples ** 2)))
                in_db = linear_to_db(in_rms)

                if not self._bypass:
                    if in_rms > 1e-6:
                        gain = self._target_linear / in_rms
                        # 防止增益過大造成爆音（最多放大 +20dB）
                        gain = min(gain, db_to_linear(20.0))
                        normalized = samples * gain
                        # 最終 hard clip 防止超過 0dBFS
                        normalized = np.clip(normalized, -1.0, 1.0)
                    else:
                        # 靜音時直接輸出靜音
                        normalized = samples
                    clipped = normalized
                else:
                    clipped = samples

                out_rms = float(np.sqrt(np.mean(clipped ** 2)))
                out_db = linear_to_db(out_rms)
                gr_db = out_db - in_db  # gain reduction (negative = reducing)

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
