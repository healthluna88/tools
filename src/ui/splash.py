from __future__ import annotations

from PySide6.QtCore    import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPixmap, QPen
from PySide6.QtWidgets import QSplashScreen

from app.util import get_resource_path


class CustomSplashScreen(QSplashScreen):

    def __init__(self):

        super().__init__(QPixmap(get_resource_path("splash.png")))

    def drawContents(self, painter):

        super().drawContents(painter)

        painter.setFont(QFont("Yuanti SC", 32, QFont.Weight.Light))
        painter.setPen(QPen(QColor("#000000")))

        rect = self.rect()

        painter.drawText \
            (
                QRect(0, rect.height() - 54, rect.width(), 40),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                "晶  准  健  康  医  学  研  究"
            )
