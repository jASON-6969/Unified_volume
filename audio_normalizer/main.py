"""
main.py
進入點。
"""

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

try:
    import pyaudiowpatch  # noqa: F401
except ImportError:
    app = QApplication(sys.argv)
    QMessageBox.critical(
        None,
        "缺少依賴",
        "找不到 pyaudiowpatch。\n\n請先執行：\n  pip install pyaudiowpatch\n\n然後重新啟動程式。",
    )
    sys.exit(1)

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("System Audio Limiter")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
