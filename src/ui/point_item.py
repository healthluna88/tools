from PySide6.QtCore import Qt, Signal, QObject, QPointF, QRectF
from PySide6.QtGui  import QPen

from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem


class PointItem(QObject, QGraphicsEllipseItem):

    position_changed = Signal(QGraphicsEllipseItem, QPointF)

    request_delete = Signal(QGraphicsEllipseItem)

    def __init__(self, r: int = 6):

        QObject.__init__(self)
        QGraphicsEllipseItem.__init__(self, QRectF(-r, -r, r * 2, r * 2))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,              True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,           True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,   True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)

        self.setZValue(1.0)

        pen = QPen(Qt.GlobalColor.white)
        pen.setCosmetic(True)
        pen.setWidthF(2.0)

        self.setPen(pen)

    def set_color(self, color):

        self.setBrush(color)

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.RightButton:

            self.request_delete.emit(self)

            event.accept()

            return

        super().mousePressEvent(event)

    def itemChange(self, change, value):

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:

            self.position_changed.emit(self, value)

        return super().itemChange(change, value)

