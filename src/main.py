from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore    import Qt, QStandardPaths
from PySide6.QtGui     import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from core.ai.segmenter import Segmenter

from ui.window import Window


def splash_pixmap():

    font = QFont("Arial", 32, QFont.Weight.Bold)

    pixmap = QPixmap(500, 300)
    pixmap.fill(QColor("#333333"))

    painter = QPainter(pixmap)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "晶准医学影像标注")
    painter.end()

    return pixmap


def main() -> None:

    logging.basicConfig(level = logging.INFO, format = '[%(levelname)s] %(name)s: %(message)s')

    app = QApplication(sys.argv)

    splash = QSplashScreen(splash_pixmap())
    splash.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    splash.show()

    def update_splash(message):

        splash.showMessage(f"{message}", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, QColor("white"))

        app.processEvents()

    update_splash("Initializing AI ...")

    try:

        segmenter = Segmenter()

    except Exception as e:

        segmenter = None

        logging.error(f"Failed to load Segmenter: {e}")

    update_splash("Initializing window ...")

    cache_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation), 'jz')

    window = Window(cache_dir, "https://annotation.capitalbioai.com/", segmenter = segmenter)
    window.showMaximized()

    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":

    main()
