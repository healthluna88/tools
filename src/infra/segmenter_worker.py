from __future__ import annotations
import cv2
import logging

import numpy as np

from PySide6.QtCore import Qt, Signal, Slot, QObject

from core.ai.segmenter import Segmenter
from core.types import ImageU8, MaskBool
from core.process.pipeline import Pipeline


logger = logging.getLogger(__name__)


class Worker(QObject):

    progress = Signal(int)

    status = Signal(str)

    generate_embedding = Signal(np.ndarray)

    segment_mask = Signal(np.ndarray)

    generate_polygon = Signal(object, object)

    _update_image    = Signal(dict)
    _update_points   = Signal(dict)
    _update_pipeline = Signal(dict)

    def __init__(self) -> None:

        super().__init__()

        self._segmenter = Segmenter()

        self._cache_image = None

        self._cache_mask_sam      = None
        self._cache_mask_pipeline = None

        self._update_image   .connect(self._on_update_image,    Qt.ConnectionType.QueuedConnection)
        self._update_points  .connect(self._on_update_points,   Qt.ConnectionType.QueuedConnection)
        self._update_pipeline.connect(self._on_update_pipeline, Qt.ConnectionType.QueuedConnection)

    def update_image(self, params):

        self._update_image.emit(params)

    def update_points(self, params):

        self._update_points.emit(params)

    def update_pipeline(self, params):

        self._update_pipeline.emit(params)

    @Slot(dict)
    def _on_update_image(self, params: dict):

        image          = params["image"    ]
        embedding      = params["embedding"]
        embedding_path = params["embedding_path"]
        points         = params["points"   ]
        pipeline       = params["pipeline" ]

        skip_polygons = params.get("skip_polygons", False)

        if embedding is None:

            embedding = self._segmenter.set_image(image, None)

            np.save(embedding_path, embedding)

            self.generate_embedding.emit(embedding)

        else:

            self._segmenter.set_image(image, embedding)

        self._cache_image = image

        self._segment(image, points, pipeline, skip_polygons)

    @Slot(dict)
    def _on_update_points(self, params: dict):

        image    = self._cache_image
        points   = params["points"  ]
        pipeline = params["pipeline"]

        self._segment(image, points, pipeline)

    @Slot(dict)
    def _on_update_pipeline(self, params: dict):

        image    = self._cache_image
        mask_sam = self._cache_mask_sam

        if image is not None and mask_sam is not None:

            pipeline = params["pipeline"]

            mask_pipeline = pipeline.process(image, mask_sam)

            self._cache_mask_pipeline = mask_pipeline

            rgba_mask = Worker._render_overlay(mask_pipeline > 0)

            self.segment_mask.emit(rgba_mask)

            self._generate_polygons(image, mask_pipeline)

    def _segment(self, image, points, pipeline: Pipeline, skip_polygons = False):

        self._cache_image = image

        if any(p["label"] == 1 for p in points):

            # SAM 输出基础 mask

            mask_sam = self._segmenter.predict(points).astype(np.uint8) * 255

            self._cache_mask_sam = mask_sam

            # 图像处理流水线修整 roi mask

            mask_pipeline = pipeline.process(image, mask_sam)

            self._cache_mask_pipeline = mask_pipeline

            # 渲染可视化遮罩

            rgba_overlay = Worker._render_overlay(mask_pipeline > 0)

            self.segment_mask.emit(rgba_overlay)

            if not skip_polygons:

                self._generate_polygons(image, mask_pipeline)

        else:

            self.segment_mask.emit(None)

            self.generate_polygon.emit(None, None)

    def _generate_polygons(self, image: ImageU8, mask: MaskBool) -> None:

        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []

        for cnt in contours:

            epsilon = 0.01 * cv2.arcLength(cnt, True)  # 控制简化程度
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            approx = approx.squeeze(1)
            polygons.append(approx)

        self.generate_polygon.emit(image, polygons)

    @staticmethod
    def _render_overlay(mask: MaskBool) -> ImageU8:

        height, width = mask.shape

        rgba_overlay = np.zeros((height, width, 4), dtype = np.uint8)

        rgba_overlay[mask] = (0, 255, 0, 100)

        return rgba_overlay
