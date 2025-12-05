"""
RenderQ GUI - PySide6 图形界面
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from .main_window import MainWindow
from .qss import QSS_THEME


def main():
    """启动GUI"""
    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("RenderQ")
    app.setOrganizationName("RenderQ")

    # 设置样式引擎
    app.setStyle("Fusion")

    # 设置默认字体为 Mi Sans
    font_families = ["Mi Sans", "MiSans", "微软雅黑", "Segoe UI", "Arial"]
    default_font = None

    for family in font_families:
        font = QFont(family)
        if QFontDatabase.hasFamily(family) or font.exactMatch():
            default_font = QFont(family, 10)
            break

    if default_font is None:
        default_font = QFont("微软雅黑", 10)

    app.setFont(default_font)

    # 应用样式表
    app.setStyleSheet(QSS_THEME)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
