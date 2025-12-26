from __future__ import annotations

import json
import logging

from pathlib import Path
from typing import List, Optional

import numpy as np

from .types import ImageU8, EmbeddingF32, MaskBool, PointSAM

from .process.pipeline import Pipeline

from ui.util import load_image_pil


from ui.validation import \
(
    points_norm_to_px,
    points_px_to_norm,
    polygons_norm_to_px,
    polygons_px_to_norm,
    validate_embedding_f32,
    validate_image_u8,
)


logger = logging.getLogger(__name__)


class Workspace:

    def __init__(self) -> None:

        self.image:          Optional[ImageU8]      = None
        self.image_path:     Optional[str]          = None

        self.embedding:      Optional[EmbeddingF32] = None
        self.embedding_path: Optional[str]          = None

        self.mask: Optional[MaskBool] = None

        self.points:   List[PointSAM] = []
        self.pipeline: Pipeline = Pipeline()
        self.polygons: List[list[list[int]]] = []

    def load(self, path_image: str | Path) -> None:

        self._clear()

        path_image     = Path(path_image)
        path_embedding = path_image.with_suffix(".embedding.npy")

        if path_image.exists():

            path_image = str(path_image.resolve())

            self.image = validate_image_u8(load_image_pil(path_image))

            if path_embedding.exists():

                path_embedding = str(path_embedding.resolve())
                self.embedding = validate_embedding_f32(np.load(path_embedding))

            else:

                self.points = []
                self.pipeline = Pipeline()
                self.polygons = []

        self.image_path     = path_image
        self.embedding_path = path_embedding

    def load_from(self, data: dict) -> None:

        data = data.get("v0") or {}

        h, w = self.image.shape[:2]

        self.points   = points_norm_to_px(data.get("sam", []) or [], width = w, height = h)
        self.pipeline = Pipeline.from_dict(data.get("pipeline", Pipeline().to_dict()))
        self.polygons = polygons_norm_to_px(data.get("polygons", []) or [], width = w, height = h)

    def save(self) -> None:

        if self.image_path is None or self.image is None:

            return

    def export_remote_annotations(self) -> dict:

        if self.image_path is None or self.image is None:

            v0 = { "sam": [], "polygons": [], "pipeline": { } }

        else:

            h, w = self.image.shape[:2]

            points   =   points_px_to_norm(self.points,   width = w, height = h)
            polygons = polygons_px_to_norm(self.polygons, width = w, height = h)

            v0 = { "sam": points, "polygons": polygons, "pipeline": self.pipeline.to_dict() }

        return { "v0": v0 }

    def save_embedding(self) -> None:

        if self.embedding is not None:

            np.save(self.embedding_path, self.embedding)

    def _clear(self) -> None:

        self.image     = None
        self.embedding = None
        self.mask      = None

        self.points   = []
        self.pipeline = Pipeline()
        self.polygons = []

        self.image_path = None
        self.embedding_path = None
