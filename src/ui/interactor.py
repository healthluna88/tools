from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsPathItem

from .point_item import PointItem


class Interactor(QObject):
    """Viewer 的交互器基类。

    - attach/detach 由 Viewer 负责调用
    - 事件处理接口返回 True 表示已处理，不再传递给 Viewer 默认行为
    """

    def __init__(self, parent = None):
        super().__init__(parent)
        self.viewer = None

    def attach(self, viewer) -> None:
        self.viewer = viewer
        self.on_attach()

    def detach(self) -> None:
        if self.viewer:
            self.on_detach()
            self.viewer = None

    def on_attach(self) -> None:
        pass

    def on_detach(self) -> None:
        pass

    def mousePressEvent(self, event) -> bool:  # noqa: N802
        return False

    def mouseMoveEvent(self, event) -> bool:  # noqa: N802
        return False

    def mouseReleaseEvent(self, event) -> bool:  # noqa: N802
        return False

    def mouseDoubleClickEvent(self, event) -> bool:  # noqa: N802
        return False

    def wheelEvent(self, event) -> bool:  # noqa: N802
        return False


class SegmentationInteractor(Interactor):
    points_updated = Signal(list)

    def __init__(self, parent = None):
        super().__init__(parent)
        self._items: dict[PointItem, dict] = { }  # {PointItem: {"x":..,"y":..,"label":..}}
        self._cached_mask = None  # 缓存当前的 overlay (rgba)

    def on_attach(self) -> None:
        scene = self.viewer.scene()
        for item in self._items.keys():
            if item.scene() != scene:
                scene.addItem(item)

        self.viewer.set_mask(self._cached_mask)

    def on_detach(self) -> None:
        scene = self.viewer.scene()
        for item in self._items.keys():
            scene.removeItem(item)
        self.viewer.set_mask(None)

    def mouseDoubleClickEvent(self, event) -> bool:  # noqa: N802
        label = 0 if event.modifiers() & Qt.KeyboardModifier.AltModifier else 1
        pos = self.viewer.mapToScene(event.pos())
        self._point_add(pos.x(), pos.y(), label)
        self._notify_points_updated()
        return True

    @Slot(list)
    def set_points(self, points: list[dict]) -> None:
        # 清理旧对象
        if self.viewer:
            scene = self.viewer.scene()
            for item in list(self._items.keys()):
                scene.removeItem(item)
                item.deleteLater()
        else:
            for item in list(self._items.keys()):
                item.deleteLater()

        self._items = { }

        for point in points:
            self._point_add(
                point["x"],
                point["y"],
                point["label"],
                add_to_scene = bool(self.viewer),
            )

    @Slot(object)
    def set_mask(self, mask) -> None:
        self._cached_mask = mask
        if self.viewer:
            self.viewer.set_mask(mask)

    @Slot(object, QPointF)
    def _point_move(self, point, value: QPointF) -> None:
        if point in self._items:
            self._items[point]["x"] = value.x()
            self._items[point]["y"] = value.y()
            self._notify_points_updated()

    @Slot(object)
    def _point_remove(self, point) -> None:
        if self.viewer:
            self.viewer.scene().removeItem(point)

        point.deleteLater()
        if point in self._items:
            del self._items[point]
            self._notify_points_updated()

    def _point_add(self, x: float, y: float, label: int, *, add_to_scene: bool = True) -> None:
        p = PointItem()
        p.setPos(x, y)
        p.set_color(QColor("#FFD5D8") if label == 1 else QColor("#000000"))

        p.position_changed.connect(self._point_move)
        p.request_delete.connect(self._point_remove)

        if add_to_scene and self.viewer:
            self.viewer.scene().addItem(p)

        self._items[p] = { "x": x, "y": y, "label": label }

    def _notify_points_updated(self) -> None:
        self.points_updated.emit(list(self._items.values()))


def smooth_closed_path(points: list[QPointF], smooth: float = 0.15) -> QPainterPath:
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
    def __init__(self) -> None:
        self.points: list[PointItem] = []
        self.path_item: QGraphicsPathItem | None = None


class PolygonInteractor(Interactor):
    final_mask = Signal(np.ndarray, np.ndarray)  # image, mask
    polygons_updated = Signal(list)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.polygons: list[PolygonData] = []

    def on_attach(self) -> None:
        scene = self.viewer.scene()
        for poly in self.polygons:
            if poly.path_item and poly.path_item.scene() != scene:
                scene.addItem(poly.path_item)
            for p in poly.points:
                if p.scene() != scene:
                    scene.addItem(p)
        self._notify_mask_update()

    def on_detach(self) -> None:
        scene = self.viewer.scene()
        for poly in self.polygons:
            if poly.path_item:
                scene.removeItem(poly.path_item)
            for p in poly.points:
                scene.removeItem(p)

    def force_update(self) -> None:
        self._notify_mask_update()

    def mouseDoubleClickEvent(self, event) -> bool:  # noqa: N802
        scene_pos = self.viewer.mapToScene(event.pos())

        for poly in self.polygons:
            idx, new_pos = self._find_insert_position(poly, scene_pos)
            if idx is not None:
                self._insert_point(poly, idx, new_pos)
                return True
        return False

    @Slot(list)
    def set_polygons(self, polygons) -> None:
        self._clear_items()

        polygons = polygons or []
        for contour in polygons:
            if len(contour) < 3:
                continue

            poly = PolygonData()

            for pos in contour:
                pt = PointItem()
                pt.setPos(pos[0], pos[1])
                pt.set_color(Qt.GlobalColor.red)

                pt.position_changed.connect(self._on_point_moved)
                pt.request_delete.connect(self._on_point_delete)
                poly.points.append(pt)

            path_item = QGraphicsPathItem()
            pen = QPen(Qt.GlobalColor.green)
            pen.setWidthF(2.0)
            pen.setCosmetic(True)

            path_item.setPen(pen)
            path_item.setBrush(QBrush(Qt.GlobalColor.transparent))
            path_item.setZValue(0.0)

            poly.path_item = path_item
            self.polygons.append(poly)

            self._rebuild_polygon(poly)

        if self.viewer:
            self.on_attach()
        else:
            self._notify_mask_update()

    def _clear_items(self) -> None:
        if self.viewer:
            scene = self.viewer.scene()
            for poly in self.polygons:
                if poly.path_item:
                    scene.removeItem(poly.path_item)
                for p in poly.points:
                    scene.removeItem(p)

        for poly in self.polygons:
            for p in poly.points:
                p.deleteLater()

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

    def _rebuild_polygon(self, poly: PolygonData) -> None:
        positions = [p.pos() for p in poly.points]
        path = smooth_closed_path(positions)
        if poly.path_item:
            poly.path_item.setPath(path)

    def _on_point_moved(self, point, _) -> None:
        poly = self._find_polygon_by_point(point)
        if poly:
            self._rebuild_polygon(poly)
            self._notify_mask_update()
            self.polygons_updated.emit(self.export_polygons())

    def _on_point_delete(self, point) -> None:
        poly = self._find_polygon_by_point(point)
        if not poly:
            return

        if len(poly.points) <= 3:
            return

        poly.points.remove(point)
        if self.viewer:
            self.viewer.scene().removeItem(point)
        point.deleteLater()

        self._rebuild_polygon(poly)
        self._notify_mask_update()
        self.polygons_updated.emit(self.export_polygons())

    def _find_polygon_by_point(self, point) -> PolygonData | None:
        for poly in self.polygons:
            if point in poly.points:
                return poly
        return None

    def _find_insert_position(self, poly: PolygonData, click_pos: QPointF):
        if not poly.path_item:
            return None, None
        path = poly.path_item.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(40.0)

        if not stroker.createStroke(path).contains(click_pos):
            return None, None

        best_i = None
        best_t = 0.0
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

    def _insert_point(self, poly: PolygonData, index: int, pos: QPointF) -> None:
        pt = PointItem()
        pt.setPos(pos)
        pt.set_color(Qt.GlobalColor.yellow)

        pt.position_changed.connect(self._on_point_moved)
        pt.request_delete.connect(self._on_point_delete)

        if self.viewer:
            self.viewer.scene().addItem(pt)

        poly.points.insert(index, pt)
        self._rebuild_polygon(poly)
        self._notify_mask_update()
        self.polygons_updated.emit(self.export_polygons())

    @staticmethod
    def _distance_point_to_segment(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
        ab = b - a
        if ab.manhattanLength() == 0:
            return (p - a).manhattanLength(), 0.0
        t = QPointF.dotProduct(p - a, ab) / QPointF.dotProduct(ab, ab)
        t = max(0.0, min(1.0, t))
        proj = a + ab * t
        return (p - proj).manhattanLength(), t

    def _notify_mask_update(self) -> None:
        if not self.viewer or self.viewer.image is None:
            return

        rect = self.viewer.scene().sceneRect()
        h = int(rect.height())
        w = int(rect.width())
        if h <= 0 or w <= 0:
            return

        mask = np.zeros((h, w), dtype = np.uint8)
        step_px = 1.0

        for poly in self.polygons:
            if not poly.path_item:
                continue

            pth = poly.path_item.path()
            length = pth.length()
            n = max(2, int(length / step_px))

            pts = [pth.pointAtPercent(i / (n - 1)) for i in range(n)]
            ply = []
            for p in pts:
                x = int(round(p.x() - rect.left()))
                y = int(round(p.y() - rect.top()))
                ply.append([x, y])

            if ply:
                ply_arr = np.array([ply], dtype = np.int32)
                cv2.fillPoly(mask, ply_arr, (255,))

        self.final_mask.emit(self.viewer.image, mask)
