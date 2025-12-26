from __future__ import annotations

import os
import sys
import logging

from PySide6.QtCore    import QStandardPaths
from PySide6.QtWidgets import QApplication

from ui.window import Window


def main() -> None:

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')

    app = QApplication(sys.argv)

    cache_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation), 'jz')

    window = Window(cache_dir, "https://annotation.capitalbioai.com/")
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":

    main()

