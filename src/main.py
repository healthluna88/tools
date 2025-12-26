from __future__ import annotations

import os
import sys
import logging

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication, QSplashScreen

from core.ai.segmenter import Segmenter

from ui.window import Window


# Helper to create a simple splash pixmap programmatically
def create_splash_pixmap():

    pixmap = QPixmap(400, 200)
    pixmap.fill(QColor("#333333"))

    painter = QPainter(pixmap)
    painter.setPen(QColor("#FFFFFF"))

    font = QFont("Arial", 20, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Annotation Tool")

    painter.end()
    return pixmap


def main() -> None:

    logging.basicConfig(level = logging.INFO, format = '[%(levelname)s] %(name)s: %(message)s')

    app = QApplication(sys.argv)

    # --- Setup Splash Screen ---
    splash_pix = create_splash_pixmap()
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()

    def update_splash(msg):

        splash.showMessage(f"\n\n\n\n{msg}", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, QColor("white"))

        app.processEvents()

    # --- Load Resources ---

    update_splash("Initializing Segmenter Model...\n(This may take a few seconds)")

    # Pre-load the heavy model here. This blocks, but that's what we want for a splash screen.
    try:

        segmenter = Segmenter()
        segmenter.init()
        print("Segmenter model initialized")

    except Exception as e:

        # Fallback if model loading fails (e.g. missing weights), allows app to open but segmentation won't work

        logging.error(f"Failed to load Segmenter: {e}")
        segmenter = None
        update_splash(f"Error loading model: {e}")

    update_splash("Initializing UI...")

    cache_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation), 'jz')

    # Pass the pre-loaded segmenter to the Window
    window = Window(cache_dir, "https://annotation.capitalbioai.com/", segmenter = segmenter)
    window.showMaximized()

    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":

    main()
