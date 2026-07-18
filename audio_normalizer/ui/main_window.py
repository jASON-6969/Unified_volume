"""
ui/main_window.py
Main window GUI with CN/EN language toggle.
"""

import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QComboBox,
    QGroupBox, QMessageBox, QStatusBar, QFrame,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.widgets import VUMeter
from audio_engine import AudioEngine


VBCABLE_URL = "https://vb-audio.com/Cable/"

STRINGS = {
    "en": {
        "window_title":     "System Audio Normalizer",
        "app_title":        "System Audio Normalizer",
        "device_group":     "Device Settings",
        "input_label":      "Input (Loopback):",
        "output_label":     "Output Device:",
        "vbcable_btn":      "Download VB-Cable (free virtual audio device)",
        "normalizer_group": "Target Volume (all audio normalized to this level)",
        "target_label":     "Target:",
        "meter_group":      "Level Monitor",
        "bypass_off":       "Bypass",
        "bypass_on":        "Bypass [ON]",
        "start":            "Start",
        "stop":             "Stop",
        "status_idle":      "Idle",
        "status_running":   "Running...",
        "status_stopped":   "Stopped",
        "status_vbcable":   "Tip: Install VB-Cable to route processed audio system-wide",
        "err_title":        "Error",
        "err_no_input":     "No valid Loopback input device selected.\nMake sure VB-Cable is installed and CABLE Input is set as Windows default output.",
        "err_no_output":    "No valid output device selected.",
        "err_start_fail":   "Failed to start",
        "err_audio":        "Audio error: ",
        "lang_btn":         "中文",
        "no_input_device":  "No loopback device found",
        "no_output_device": "No output device found",
    },
    "zh": {
        "window_title":     "系統音量正規化器",
        "app_title":        "系統音量正規化器",
        "device_group":     "裝置設定",
        "input_label":      "輸入 (Loopback):",
        "output_label":     "輸出裝置:",
        "vbcable_btn":      "下載 VB-Cable（免費虛擬音訊裝置）",
        "normalizer_group": "目標音量（所有聲音統一輸出此音量）",
        "target_label":     "目標:",
        "meter_group":      "電平監測",
        "bypass_off":       "直通",
        "bypass_on":        "直通 [開啟]",
        "start":            "啟動",
        "stop":             "停止",
        "status_idle":      "待機",
        "status_running":   "執行中...",
        "status_stopped":   "已停止",
        "status_vbcable":   "提示：安裝 VB-Cable 可將處理後音訊路由至全系統",
        "err_title":        "錯誤",
        "err_no_input":     "請選擇有效的 Loopback 輸入裝置。\n確認已安裝 VB-Cable 並將 CABLE Input 設為 Windows 預設輸出。",
        "err_no_output":    "請選擇有效的輸出裝置。",
        "err_start_fail":   "啟動失敗",
        "err_audio":        "音訊錯誤：",
        "lang_btn":         "English",
        "no_input_device":  "找不到 Loopback 裝置",
        "no_output_device": "找不到輸出裝置",
    },
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = AudioEngine()
        self._running = False
        self._lang = "zh"  # default Chinese

        self.setMinimumSize(440, 560)
        self.setStyleSheet(self._stylesheet())

        self._build_ui()
        self._populate_devices()
        self._check_vbcable()
        self._apply_lang()

        # meter update timer 20 fps
        self._timer = QTimer()
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._update_meters)
        self._timer.start()

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def _t(self, key: str) -> str:
        return STRINGS[self._lang].get(key, key)

    def _apply_lang(self):
        s = STRINGS[self._lang]
        self.setWindowTitle(s["window_title"])
        self.lbl_title.setText(s["app_title"])
        self.grp_device.setTitle(s["device_group"])
        self.lbl_input.setText(s["input_label"])
        self.lbl_output.setText(s["output_label"])
        self.btn_vbcable.setText(s["vbcable_btn"])
        self.grp_normalizer.setTitle(s["normalizer_group"])
        self.lbl_target_key.setText(s["target_label"])
        self.grp_meter.setTitle(s["meter_group"])
        self.btn_lang.setText(s["lang_btn"])
        self.btn_bypass.setText(
            s["bypass_on"] if self.btn_bypass.isChecked() else s["bypass_off"]
        )
        self.btn_toggle.setText(s["stop"] if self._running else s["start"])
        # refresh status bar text only when idle/stopped
        if not self._running:
            self.status_bar.showMessage(s["status_idle"])

    def _on_lang_toggle(self):
        self._lang = "en" if self._lang == "zh" else "zh"
        self._apply_lang()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # top bar: title + lang button
        top_row = QHBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.lbl_title, stretch=1)

        self.btn_lang = QPushButton()
        self.btn_lang.setFixedWidth(72)
        self.btn_lang.setObjectName("langButton")
        self.btn_lang.clicked.connect(self._on_lang_toggle)
        top_row.addWidget(self.btn_lang)
        root.addLayout(top_row)

        root.addWidget(self._make_separator())

        # device group
        self.grp_device = QGroupBox()
        dev_layout = QVBoxLayout(self.grp_device)

        self.lbl_input = QLabel()
        dev_layout.addWidget(self.lbl_input)
        self.combo_input = QComboBox()
        dev_layout.addWidget(self.combo_input)

        self.lbl_output = QLabel()
        dev_layout.addWidget(self.lbl_output)
        self.combo_output = QComboBox()
        dev_layout.addWidget(self.combo_output)

        self.btn_vbcable = QPushButton()
        self.btn_vbcable.setObjectName("linkButton")
        self.btn_vbcable.clicked.connect(lambda: webbrowser.open(VBCABLE_URL))
        self.btn_vbcable.setVisible(False)
        dev_layout.addWidget(self.btn_vbcable)

        root.addWidget(self.grp_device)

        # normalizer group
        self.grp_normalizer = QGroupBox()
        lim_layout = QVBoxLayout(self.grp_normalizer)

        threshold_row = QHBoxLayout()
        self.lbl_target_key = QLabel()
        threshold_row.addWidget(self.lbl_target_key)
        self.label_threshold = QLabel("-10.0 dBFS")
        self.label_threshold.setMinimumWidth(90)
        threshold_row.addWidget(self.label_threshold)
        threshold_row.addStretch()
        lim_layout.addLayout(threshold_row)

        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setMinimum(-600)   # -60.0 dB
        self.slider_threshold.setMaximum(0)       # 0.0 dB
        self.slider_threshold.setValue(-100)      # -10.0 dB default
        self.slider_threshold.setTickInterval(100)
        self.slider_threshold.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_threshold.valueChanged.connect(self._on_threshold_changed)
        lim_layout.addWidget(self.slider_threshold)

        tick_row = QHBoxLayout()
        for lbl_text in ["-60", "-50", "-40", "-30", "-20", "-10", "0"]:
            lbl = QLabel(lbl_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setStyleSheet("font-size: 9px; color: #888;")
            tick_row.addWidget(lbl)
        lim_layout.addLayout(tick_row)

        root.addWidget(self.grp_normalizer)

        root.addWidget(self._make_separator())

        # meters
        self.grp_meter = QGroupBox()
        meter_row = QHBoxLayout(self.grp_meter)
        meter_row.setSpacing(16)

        # dB scale
        scale_col = QVBoxLayout()
        scale_col.setSpacing(0)
        for db_lbl in ["0", "-6", "-12", "-18", "-30", "-60"]:
            l = QLabel(db_lbl)
            l.setStyleSheet("font-size: 9px; color: #666;")
            scale_col.addWidget(l)
        meter_row.addLayout(scale_col)

        self.vu_in = VUMeter("IN")
        self.vu_out = VUMeter("OUT")
        self.vu_gr = VUMeter("GR")

        for vu in (self.vu_in, self.vu_out, self.vu_gr):
            vu.setMinimumHeight(150)
            meter_row.addWidget(vu, alignment=Qt.AlignmentFlag.AlignHCenter)

        root.addWidget(self.grp_meter)

        root.addWidget(self._make_separator())

        # bypass + start/stop
        ctrl_row = QHBoxLayout()

        self.btn_bypass = QPushButton()
        self.btn_bypass.setCheckable(True)
        self.btn_bypass.setObjectName("bypassButton")
        self.btn_bypass.toggled.connect(self._on_bypass_toggled)
        ctrl_row.addWidget(self.btn_bypass)

        ctrl_row.addStretch()

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("startButton")
        self.btn_toggle.setMinimumWidth(100)
        self.btn_toggle.clicked.connect(self._on_toggle)
        ctrl_row.addWidget(self.btn_toggle)

        root.addLayout(ctrl_row)

        # status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _make_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        return line

    # ------------------------------------------------------------------
    # Device population
    # ------------------------------------------------------------------

    def _populate_devices(self):
        self.combo_input.clear()
        self.combo_output.clear()

        loopbacks = self.engine.get_loopback_devices()
        if not loopbacks:
            self.combo_input.addItem(self._t("no_input_device"), -1)
        else:
            for d in loopbacks:
                self.combo_input.addItem(d["name"], d["index"])

        outputs = self.engine.get_output_devices()
        if not outputs:
            self.combo_output.addItem(self._t("no_output_device"), -1)
        else:
            for d in outputs:
                # skip loopback devices and VB-Cable Input from output list
                # Bug 4 fix: 原條件 "CABLE IN 1" 無法匹配實際裝置名 "CABLE Input"
                name_up = d["name"].upper()
                if "LOOPBACK" in name_up or "CABLE INPUT" in name_up:
                    continue
                self.combo_output.addItem(d["name"], d["index"])

        # default output: prefer real speaker over VB-Cable
        for i in range(self.combo_output.count()):
            name_up = self.combo_output.itemText(i).upper()
            if "VB-CABLE" not in name_up and "CABLE" not in name_up:
                self.combo_output.setCurrentIndex(i)
                break

    def _check_vbcable(self):
        if not self.engine.has_vbcable():
            self.btn_vbcable.setVisible(True)
        self.status_bar.showMessage(self._t("status_idle"))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_threshold_changed(self, value: int):
        db = value / 10.0
        self.label_threshold.setText(f"{db:.1f} dBFS")
        self.engine.set_threshold_db(db)

    def _on_bypass_toggled(self, checked: bool):
        self.engine.set_bypass(checked)
        self.btn_bypass.setText(
            self._t("bypass_on") if checked else self._t("bypass_off")
        )

    def _on_toggle(self):
        if not self._running:
            loopback_idx = self.combo_input.currentData()
            output_idx = self.combo_output.currentData()

            if loopback_idx is None or loopback_idx == -1:
                QMessageBox.warning(self, self._t("err_title"), self._t("err_no_input"))
                return
            if output_idx is None or output_idx == -1:
                QMessageBox.warning(self, self._t("err_title"), self._t("err_no_output"))
                return

            try:
                self.engine.start(loopback_idx, output_idx)
                self._running = True
                self.btn_toggle.setText(self._t("stop"))
                self.btn_toggle.setObjectName("stopButton")
                self.btn_toggle.setStyleSheet("")
                self.combo_input.setEnabled(False)
                self.combo_output.setEnabled(False)
                self.status_bar.showMessage(self._t("status_running"))
            except Exception as e:
                QMessageBox.critical(self, self._t("err_start_fail"), str(e))
        else:
            self.engine.stop()
            self._running = False
            self.btn_toggle.setText(self._t("start"))
            self.btn_toggle.setObjectName("startButton")
            self.btn_toggle.setStyleSheet("")
            self.combo_input.setEnabled(True)
            self.combo_output.setEnabled(True)
            self.vu_in.set_db(-60)
            self.vu_out.set_db(-60)
            self.vu_gr.set_db(-60)
            self.status_bar.showMessage(self._t("status_stopped"))

    def _update_meters(self):
        q = self.engine.meter_queue
        latest = None
        while not q.empty():
            try:
                latest = q.get_nowait()
            except Exception:
                break

        if latest is None:
            return

        if isinstance(latest, tuple) and latest[0] == "error":
            self.status_bar.showMessage(self._t("err_audio") + str(latest[1]))
            if self._running:
                self._on_toggle()
            return

        in_db, out_db, gr_db = latest
        self.vu_in.set_db(in_db)
        self.vu_out.set_db(out_db)
        self.vu_gr.set_db(gr_db)

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _stylesheet(self):
        return """
        QMainWindow, QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QGroupBox {
            border: 1px solid #444;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            color: #aaa;
        }
        QComboBox {
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px 8px;
            color: #e0e0e0;
        }
        QComboBox::drop-down { border: none; }
        QComboBox QAbstractItemView {
            background-color: #2d2d2d;
            color: #e0e0e0;
            selection-background-color: #0078d4;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #3a3a3a;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #0078d4;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }
        QSlider::sub-page:horizontal {
            background: #0078d4;
            border-radius: 3px;
        }
        QPushButton {
            background-color: #2d2d2d;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px 16px;
            color: #e0e0e0;
        }
        QPushButton:hover { background-color: #3a3a3a; }
        QPushButton#startButton {
            background-color: #0078d4;
            border: none;
            color: white;
            font-weight: bold;
        }
        QPushButton#startButton:hover { background-color: #006cbd; }
        QPushButton#stopButton {
            background-color: #c42b1c;
            border: none;
            color: white;
            font-weight: bold;
        }
        QPushButton#stopButton:hover { background-color: #b02010; }
        QPushButton#bypassButton:checked {
            background-color: #ca8a00;
            color: white;
            border: none;
        }
        QPushButton#linkButton {
            color: #4ea3e0;
            border: 1px dashed #4ea3e0;
            background: transparent;
        }
        QPushButton#linkButton:hover { background-color: #1a2a3a; }
        QPushButton#langButton {
            background-color: #333;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 4px 10px;
            color: #ccc;
            font-size: 11px;
        }
        QPushButton#langButton:hover { background-color: #3a3a3a; }
        QStatusBar { color: #888; font-size: 11px; }
        QLabel { color: #e0e0e0; }
        """

    def closeEvent(self, event):
        self.engine.close()
        event.accept()
