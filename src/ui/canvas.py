import cv2
import numpy as np

from PySide6.QtCore import Signal, Slot, QPointF, QRectF, Qt, QPoint
from PySide6.QtGui import QColor, QBrush, QPen, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene, QGraphicsPathItem

from .point_item import PointItem
from .viewer import Viewer


def smooth_closed_path(points, smooth = 0.15):
    n = len(points)
    if n < 3:
        return QPainterPath()

    path = QPainterPath()
    path.moveTo(points[0])

    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]

        c1 = p1 + (p2 - p0) * smooth
        c2 = p2 - (p3 - p1) * smooth

        path.cubicTo(c1, c2, p2)

    path.closeSubpath()
    return path


class PolygonData:
    def __init__(self):
        self.points = []  # list[PointItem]
        self.path_item = None  # QGraphicsPathItem


class Canvas(Viewer):

    final_mask = Signal(np.ndarray, np.ndarray)

    polygons_updated = Signal(list)

    def __init__(self, smooth = 0.15):

        super().__init__()

        self.polygons = []  # list[PolygonData]

    def clear(self):

        """
        polygons : list[list[QPointF]]
        """

        for poly in self.polygons:

            if poly.path_item:

                self.scene().removeItem(poly.path_item)

            for p in poly.points:

                self.scene().removeItem(p)

        self.polygons.clear()
    
    def export_polygons(self) -> list:

        ret = []
        for poly in self.polygons:
            if not poly.points:
                continue
            contour = []
            for p in poly.points:
                pos = p.pos()
                contour.append([float(pos.x()), float(pos.y())])
            if len(contour) >= 3:
                ret.append(contour)
        return ret

    @Slot(list)
    def set_polygons(self, polygons):

        self.clear()

        if polygons is None:

            polygons = []

        for contour in polygons:

            if len(contour) < 3:

                continue

            poly = PolygonData()

            # 创建 PointItem

            for pos in contour:

                pt = PointItem()
                pt.setPos(pos[0], pos[1])
                pt.set_color(Qt.GlobalColor.red)

                pt.position_changed.connect(self._on_point_moved)
                pt.request_delete.connect(self._on_point_delete)

                self.scene().addItem(pt)
                poly.points.append(pt)

            # 创建 path
            path_item = QGraphicsPathItem()
            pen = QPen(Qt.GlobalColor.green)
            pen.setWidthF(2.0)
            pen.setCosmetic(True)

            path_item.setPen(pen)
            path_item.setBrush(QBrush(Qt.GlobalColor.transparent))
            path_item.setZValue(0.0)

            self.scene().addItem(path_item)
            poly.path_item = path_item

            self.polygons.append(poly)

            self._rebuild_polygon(poly)

        self.path_to_mask()

    def mouseDoubleClickEvent(self, event):

        scene_pos = self.mapToScene(event.pos())

        for poly in self.polygons:

            idx, new_pos = self._find_insert_position(poly, scene_pos)

            if idx is not None:

                self._insert_point(poly, idx, new_pos)

                return

        super().mouseDoubleClickEvent(event)

    def _rebuild_polygon(self, poly: PolygonData):

        positions = [p.pos() for p in poly.points]

        path = smooth_closed_path(positions)

        poly.path_item.setPath(path)

    def _on_point_moved(self, point, _):

        poly = self._find_polygon_by_point(point)

        if poly:

            self._rebuild_polygon(poly)
            self.path_to_mask()
            self.polygons_updated.emit(self.export_polygons())

    def _on_point_delete(self, point):
        poly = self._find_polygon_by_point(point)
        if not poly:
            return

        if len(poly.points) <= 3:
            return  # 最少 3 个点

        poly.points.remove(point)
        self.scene().removeItem(point)
        self._rebuild_polygon(poly)
        self.path_to_mask()
        self.polygons_updated.emit(self.export_polygons())

    def _find_polygon_by_point(self, point):
        for poly in self.polygons:
            if point in poly.points:
                return poly
        return None

    def _find_insert_position(self, poly, click_pos):
        path = poly.path_item.path()

        stroker = QPainterPathStroker()
        stroker.setWidth(40.0)

        if not stroker.createStroke(path).contains(click_pos):

            return None, None

        best_i = None
        best_t = 0
        best_dist = float("inf")

        pts = [p.pos() for p in poly.points]
        n = len(pts)

        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]

            dist, t = self._distance_point_to_segment(click_pos, a, b)
            if dist < best_dist:
                best_dist = dist
                best_i = i
                best_t = t

        new_pos = pts[best_i] * (1 - best_t) + pts[(best_i + 1) % n] * best_t
        return best_i + 1, new_pos

    def _insert_point(self, poly, index, pos):
        pt = PointItem()
        pt.setPos(pos)
        pt.set_color(Qt.GlobalColor.yellow)

        pt.position_changed.connect(self._on_point_moved)
        pt.request_delete.connect(self._on_point_delete)

        self.scene().addItem(pt)
        poly.points.insert(index, pt)

        self._rebuild_polygon(poly)
        self.path_to_mask()
        self.polygons_updated.emit(self.export_polygons())

    @staticmethod
    def _distance_point_to_segment(p, a, b):

        ab = b - a

        if ab.manhattanLength() == 0:

            return (p - a).manhattanLength(), 0.0

        t = QPointF.dotProduct(p - a, ab) / QPointF.dotProduct(ab, ab)
        t = max(0.0, min(1.0, t))

        proj = a + ab * t

        return (p - proj).manhattanLength(), t

    def path_to_mask(self):

        rect = self.sceneRect()

        h = int(rect.height())
        w = int(rect.width())

        mask = np.zeros((h, w), dtype = np.uint8)

        step_px = 1.0

        for poly in self.polygons:

            if poly.path_item:

                pth = poly.path_item.path()
                length = pth.length()
                n = max(2, int(length / step_px))

                pts = []
                for i in range(n):
                    t = i / (n - 1)
                    p = pth.pointAtPercent(t)
                    pts.append(p)

                ply = []
                for p in pts:
                    x = int(round(p.x() - rect.left()))
                    y = int(round(p.y() - rect.top()))
                    ply.append([x, y])

                ply = np.array([ply], dtype = np.int32)

                cv2.fillPoly(mask, ply, (255, ))

        # self.polygons_updated.emit(self.export_polygons())

        self.final_mask.emit(self.image, mask)

