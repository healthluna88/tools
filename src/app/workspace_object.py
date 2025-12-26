from __future__ import annotations

from PySide6.QtCore import QObject

from core.workspace import Workspace


class WorkspaceObject(QObject):
    """Qt wrapper around :class:`workspace_core.Workspace`.

    The UI expects a QObject with signals. All logic lives in Workspace to keep
    the data model testable without a Qt runtime.
    """

    def __init__(self) -> None:

        super().__init__()

        self.core = Workspace()

    # Properties are proxied for backwards compatibility
    @property
    def image(self):
        return self.core.image

    @property
    def embedding(self):
        return self.core.embedding

    @property
    def embedding_path(self):
        return self.core.embedding_path

    @property
    def points(self):
        return self.core.points

    @property
    def pipeline(self):
        return self.core.pipeline

    @property
    def polygons(self):
        return self.core.polygons

    @embedding.setter
    def embedding(self, embedding) -> None:
        self.core.embedding = embedding

    @points.setter
    def points(self, points) -> None:
        self.core.points = points  # legacy: UI mutates directly

    @pipeline.setter
    def pipeline(self, pipeline) -> None:
        self.core.pipeline = pipeline

    @polygons.setter
    def polygons(self, polygons) -> None:
        self.core.polygons = polygons

    def set_embedding(self, embedding) -> None:
        """Legacy setter used by controller."""
        self.embedding = embedding
        # self.core.save_embedding()

    def set_points(self, points) -> None:
        """Legacy setter used by controller."""
        self.points = points

    def set_polygons(self, polygons) -> None:
        """Legacy setter used by controller."""
        self.polygons = polygons

    def load(self, path_image):
        self.core.load(path_image)

    def load_from(self, data):
        self.core.load_from(data)

    def export_remote_annotations(self) -> dict:
        return self.core.export_remote_annotations()
