from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QObject  # 引入 Qt 支持

from core.types import ImageU8, EmbeddingF32, MaskBool, PointSAM
from core.process.pipeline import Pipeline
from ui.util import load_image_pil
from ui.validation import (
    points_norm_to_px,
    points_px_to_norm,
    polygons_norm_to_px,
    polygons_px_to_norm,
    validate_embedding_f32,
    validate_image_u8,
)

logger = logging.getLogger(__name__)


class Workspace(QObject):
    """
    合并后的 Workspace，既是核心数据模型，也是 Qt 对象。
    """

    # 如果未来需要属性变化的细粒度信号，可以在这里定义
    # distinct_changed = Signal()

    def __init__(self) -> None:
        super().__init__()  # QObject 初始化

        self.image: Optional[ImageU8] = None
        self.image_path: Optional[str] = None

        self.embedding: Optional[EmbeddingF32] = None
        self.embedding_path: Optional[str] = None

        self.mask: Optional[MaskBool] = None

        self.points: List[PointSAM] = []
        self.pipeline: Pipeline = Pipeline()
        self.polygons: List[list[list[int]]] = []

    def load(self, path_image: str | Path) -> None:

        self._clear()

        path_image = Path(path_image)
        path_embedding = path_image.with_suffix(".embedding.npy")

        if path_image.exists():

            resolved_path = str(path_image.resolve())

            self.image = validate_image_u8(load_image_pil(resolved_path))

            if path_embedding.exists():
                path_embedding_str = str(path_embedding.resolve())
                self.embedding = validate_embedding_f32(np.load(path_embedding_str))
            else:
                # 新图片默认初始化
                self.points = []
                self.pipeline = Pipeline()
                self.polygons = []
        else:
            logger.error(f"Image path does not exist: {path_image}")

        self.image_path = str(path_image.resolve())
        self.embedding_path = str(path_embedding.resolve())

    def load_from(self, data: dict) -> None:
        """从 JSON 数据加载标注状态"""
        data = data.get("v0") or { }
        if self.image is None:
            return

        h, w = self.image.shape[:2]
        self.points = points_norm_to_px(data.get("sam", []) or [], width = w, height = h)
        self.pipeline = Pipeline.from_dict(data.get("pipeline", Pipeline().to_dict()))
        self.polygons = polygons_norm_to_px(data.get("polygons", []) or [], width = w, height = h)

    def export_remote_annotations(self) -> dict:
        if self.image_path is None or self.image is None:
            v0 = { "sam": [], "polygons": [], "pipeline": { } }
        else:
            h, w = self.image.shape[:2]
            points = points_px_to_norm(self.points, width = w, height = h)
            polygons = polygons_px_to_norm(self.polygons, width = w, height = h)
            v0 = { "sam": points, "polygons": polygons, "pipeline": self.pipeline.to_dict() }

        return { "v0": v0 }

    def _clear(self) -> None:
        self.image = None
        self.embedding = None
        self.mask = None
        self.points = []
        self.pipeline = Pipeline()
        self.polygons = []
        self.image_path = None
        self.embedding_path = None

    # --- 兼容旧 API 的 Setter ---
    # Controller 可能会用到这些来更新数据

    def set_points(self, points: List[PointSAM]):
        self.points = points

    def set_polygons(self, polygons):
        self.polygons = polygons

    def set_embedding(self, embedding):
        self.embedding = embedding

    def set_pipeline(self, pipeline):
        self.pipeline = pipeline
