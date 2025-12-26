from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QThread

from infra.segmenter_worker import Worker


class SegmenterService(QObject):
    """Long-lived segmentation service."""

    status = Signal(str)
    generate_embedding = Signal(object)
    segment_mask = Signal(object)
    generate_polygon = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()

        self._thread = QThread()
        self._worker = Worker()

        self._worker.status.connect(lambda s: self.status.emit(str(s)))
        self._worker.generate_embedding.connect(self.generate_embedding)
        self._worker.segment_mask.connect(self.segment_mask)
        self._worker.generate_polygon.connect(self.generate_polygon)

        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def close(self) -> None:
        self._thread.quit()
        self._thread.wait()

    def update_image(self, payload: dict) -> None:
        self._worker.update_image(payload)

    def update_points(self, payload: dict) -> None:
        self._worker.update_points(payload)

    def update_pipeline(self, payload: dict) -> None:
        self._worker.update_pipeline(payload)
