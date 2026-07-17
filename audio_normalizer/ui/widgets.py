"""
ui/widgets.py
自訂 VU Meter 控件。
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFont


class VUMeter(QWidget):
    """
    垂直 VU Meter，顯示 -60dB 到 0dB。
    綠色: -60 ~ -18 dB
    黃色: -18 ~ -6 dB
    紅色: -6 ~ 0 dB
    """

    MIN_DB = -60.0
    MAX_DB = 0.0

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._db = -60.0
        self._label = label
        self.setMinimumSize(30, 120)
        self.setMaximumWidth(50)

    def set_db(self, db: float):
        self._db = max(self.MIN_DB, min(self.MAX_DB, db))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_h = h - 20  # leave space for label

        # background
        painter.fillRect(0, 0, w, bar_h, QColor(30, 30, 30))

        # filled ratio
        ratio = (self._db - self.MIN_DB) / (self.MAX_DB - self.MIN_DB)
        filled_h = int(bar_h * ratio)
        top_y = bar_h - filled_h

        if filled_h > 0:
            grad = QLinearGradient(0, bar_h, 0, 0)
            grad.setColorAt(0.0, QColor(0, 200, 80))    # green bottom
            grad.setColorAt(0.7, QColor(200, 200, 0))   # yellow mid
            grad.setColorAt(1.0, QColor(220, 50, 50))   # red top

            painter.fillRect(2, top_y, w - 4, filled_h, grad)

        # threshold marker at 0 dB top
        painter.setPen(QColor(255, 255, 255, 80))
        painter.drawRect(0, 0, w - 1, bar_h - 1)

        # label
        painter.setPen(QColor(200, 200, 200))
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.drawText(0, bar_h + 2, w, 18, Qt.AlignmentFlag.AlignHCenter, self._label)

        # dB text
        painter.setPen(QColor(180, 180, 180))
        font2 = QFont("Arial", 7)
        painter.setFont(font2)
        db_text = f"{self._db:.1f}"
        painter.drawText(0, top_y - 14, w, 14, Qt.AlignmentFlag.AlignHCenter, db_text)

        painter.end()
