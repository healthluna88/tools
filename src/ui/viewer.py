import numpy as np

from PySide6.QtCore import Qt, QRectF, Slot
from PySide6.QtGui import QColor, QPainter, QPixmap, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsPixmapItem

from .util import ndarray_to_qimage


class Viewer(QGraphicsView):

    def __init__(self, parent = None):

        super().__init__(parent)

        self.setBackgroundBrush(QColor("#303030"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.setRenderHints \
                (
                self.renderHints() |
                QPainter.RenderHint.Antialiasing |
                QPainter.RenderHint.SmoothPixmapTransform
            )

        scene = QGraphicsScene(self)

        self.setScene(scene)

        item_image = QGraphicsPixmapItem()
        item_image.setZValue(0)

        scene.addItem(item_image)

        item_mask = QGraphicsPixmapItem()
        item_mask.setZValue(0.5)

        scene.addItem(item_mask)

        self._item_image = item_image
        self._item_mask = item_mask

        self._scale_min = 1.0
        self._scale_current = 1.0

        self._image = None
        self._interactor = None

    def set_interactor(self, interactor):
        if self._interactor == interactor:
            return

        if self._interactor:
            self._interactor.detach()

        self._interactor = interactor

        if self._interactor:
            self._interactor.attach(self)

    @Slot(np.ndarray)
    def set_image(self, image: np.ndarray | None):

        if image is not None:
            pixmap = QPixmap.fromImage(ndarray_to_qimage(image))
            self._item_image.setPixmap(pixmap)
            self._item_image.setVisible(True)
            self.scene().setSceneRect(QRectF(pixmap.rect()))
        else:
            self._item_image.setVisible(False)
            self._scale_min = 1.0
            self._scale_current = 1.0

        if self._image is not image:
            self._image = image
            self.fit()
            # 图像变更时，通知 interactor 刷新（例如 PolygonInteractor 依赖尺寸）
            # 实际上 Interactor 通常被动等待 Window set_data，但这里可作为保险
            pass

    @property
    def image(self):
        return self._image

    @Slot(np.ndarray)
    def set_mask(self, image: np.ndarray | None):
        """设置覆盖在原图上的 Mask (通常由 SegmentationInteractor 使用)"""
        if image is not None:
            pixmap = QPixmap.fromImage(ndarray_to_qimage(image))
            self._item_mask.setPixmap(pixmap)
            self._item_mask.setVisible(True)
        else:
            self._item_mask.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def mousePressEvent(self, event: QMouseEvent):
        handled = False
        if self._interactor:
            handled = self._interactor.mousePressEvent(event)

        if not handled:
            if event.button() == Qt.MouseButton.LeftButton:
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        handled = False
        if self._interactor:
            handled = self._interactor.mouseReleaseEvent(event)

        if not handled:
            super().mouseReleaseEvent(event)
            if event.button() == Qt.MouseButton.LeftButton:
                self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # 优先让 Interactor 处理双击 (如添加点)
        handled = False
        if self._interactor:
            handled = self._interactor.mouseDoubleClickEvent(event)

        if not handled:
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        handled = False
        if self._interactor:
            handled = self._interactor.wheelEvent(event)

        if not handled:
            if self._item_image is not None:
                factor = 1.02
                factor = factor if event.angleDelta().y() > 0 else 1.0 / factor
                scale = self._scale_current * factor
                if scale < self._scale_min:
                    scale = self._scale_min
                self._scale_current = scale
                self._scale()

    def fit(self):
        vw = self.viewport().width()
        vh = self.viewport().height()

        if not self._item_image.pixmap() or self._item_image.pixmap().isNull():
            return

        pw = self._item_image.pixmap().width()
        ph = self._item_image.pixmap().height()

        if pw == 0 or ph == 0:
            return

        sx = vw / pw
        sy = vh / ph

        self._scale_min = min(sx, sy)
        self._scale_current = self._scale_min

        self.resetTransform()
        self.centerOn(self._item_image)
        self.scale(self._scale_current, self._scale_current)

    def _scale(self):
        self.resetTransform()
        self.scale(self._scale_current, self._scale_current)