from PySide6.QtCore    import Qt, Signal, Slot, QPointF
from PySide6.QtGui     import QColor
from PySide6.QtWidgets import QGraphicsEllipseItem

from .point_item  import PointItem
from .viewer import Viewer


class Annotator(Viewer):

    points_updated = Signal(list)

    def __init__(self, parent = None):

        super().__init__(parent)

        self._items = {}

    @Slot(list)
    def set_points(self, points):

        scene = self.scene()

        for item in list(self._items.keys()):

            scene.removeItem(item)

            item.deleteLater()

        self._items = {}

        for point in points:

            x = point["x"]
            y = point["y"]

            label = point["label"]

            self._point_add(x, y, label)

    def mouseDoubleClickEvent(self, event):

        super().mouseDoubleClickEvent(event)

        label = 0 if event.modifiers() & Qt.KeyboardModifier.AltModifier else 1

        pos = self.mapToScene(event.pos())

        self._point_add(pos.x(), pos.y(), label)

        # todo 这个 notify 位置需要再考虑
        self._notify_points_updated()

    def _point_add(self, x: float, y: float, label: int):

        scene = self.scene()

        p = PointItem()
        p.setPos(x, y)

        p.set_color(QColor('#FFD5D8') if label == 1 else QColor('#000000'))

        p.position_changed.connect(self._point_move)
        p.request_delete.connect(self._point_remove)

        scene.addItem(p)

        self._items[p] = ({ "x": x, "y": y, "label": label })

    @Slot(QGraphicsEllipseItem, QPointF)
    def _point_move(self, point, value):

        p = self._items[point]

        p["x"] = value.x()
        p["y"] = value.y()

        self._notify_points_updated()

    @Slot(QGraphicsEllipseItem)
    def _point_remove(self, point):

        self.scene().removeItem(point)

        point.deleteLater()

        del self._items[point]

        self._notify_points_updated()

    def _notify_points_updated(self):

        self.points_updated.emit(list(self._items.values()))

