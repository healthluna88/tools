from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore    import Qt, QStandardPaths
from PySide6.QtGui     import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from core.ai.segmenter import Segmenter
from ui.splash import CustomSplashScreen

from ui.window import Window


def main() -> None:

    logging.basicConfig(level = logging.INFO, format = '[%(levelname)s] %(name)s: %(message)s')

    app = QApplication(sys.argv)

    splash = CustomSplashScreen()
    splash.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    splash.show()

    def update_splash(message):

        splash.showMessage(f"{message}", Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, Qt.GlobalColor.gray)

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
