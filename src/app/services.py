# src/app/services.py

from __future__ import annotations
import threading
import logging
import cv2
import numpy as np

from core.ai.segmenter import Segmenter
from infra.repository import Repository

logger = logging.getLogger(__name__)


class ProjectService:
    """
    负责处理与项目数据存储相关的逻辑。
    """

    def __init__(self, repo: Repository):
        self._repo = repo

    def login(self, username, password):
        self._repo.login(username, password)

    def fetch_image_data(self, project_id, case_id, image_id) -> dict:
        return self._repo.get_image(
            project_id = project_id,
            case_id = case_id,
            image_id = image_id
        )

    # ... 其余方法保持不变 ...

    def update_annotations(self, project_id, case_id, image_id, data, status) -> dict:
        return self._repo.update(
            project_id = project_id,
            case_id = case_id,
            image_id = image_id,
            data = data,
            status = status
        )

    def list_projects(self, status: list | None = None) -> dict:
        return self._repo.list_projects(status)

    def list_cases(self, project_id: str, status: list | None = None) -> dict:
        return self._repo.list_cases(project_id, status)

    def list_images(self, project_id: str, case_id: str, status: list | None = None) -> dict:
        return self._repo.list_images(project_id, case_id, status)

    def download_image(self, image_id: str, save_path: str) -> str:
        self._repo.download_image(image_id, save_path)
        return save_path


# SegmentationService 保持不变 ...
class SegmentationService:
    def __init__(self, segmenter: Segmenter):
        self._segmenter = segmenter
        self._lock = threading.Lock()

    def segment_image(self, image: np.ndarray, embedding, embedding_path, points, pipeline) -> dict:

        with self._lock:
            seg = self._segmenter
            if seg is None:
                raise RuntimeError("Segmenter model is not initialized.")

            if embedding is None:
                embedding = seg.set_image(image, None)
                if embedding_path:
                    np.save(embedding_path, embedding)
            else:
                seg.set_image(image, embedding)

            mask_sam = None
            mask_pipeline = None
            rgba_mask = None
            polygons = None

            if any(p["label"] == 1 for p in points):
                mask_sam = seg.predict(points).astype(np.uint8) * 255
                mask_pipeline = pipeline.process(image, mask_sam)
                rgba_mask = self._render_overlay(mask_pipeline > 0)

        return {
            "type":        "image",
            "embedding":   embedding,
            "mask_sam":    mask_sam,
            "mask_binary": mask_pipeline,
            "rgba_mask":   rgba_mask,
            "polygons":    polygons,
            "image_ref":   image
        }

    def segment_points(self, image: np.ndarray, points, pipeline, compute_polygons = True) -> dict:
        with self._lock:
            seg = self._segmenter
            if seg is None:
                raise RuntimeError("Segmenter model is not initialized.")

            mask_sam = None
            mask_pipeline = None
            rgba_mask = None
            polygons = None

            if any(p["label"] == 1 for p in points):
                mask_sam = seg.predict(points).astype(np.uint8) * 255
                mask_pipeline = pipeline.process(image, mask_sam)
                rgba_mask = self._render_overlay(mask_pipeline > 0)

                if compute_polygons:
                    polygons = self._generate_polygons(image, mask_pipeline)

        return {
            "type":        "points",
            "mask_sam":    mask_sam,
            "mask_binary": mask_pipeline,
            "rgba_mask":   rgba_mask,
            "polygons":    polygons,
            "image_ref":   image
        }

    def segment_pipeline(self, image: np.ndarray, mask_sam, pipeline, compute_polygons = True) -> dict:
        if mask_sam is None:
            return {
                "type":        "pipeline",
                "mask_binary": None,
                "rgba_mask":   None,
                "polygons":    None,
                "image_ref":   image
            }

        mask_pipeline = pipeline.process(image, mask_sam)
        rgba_mask = self._render_overlay(mask_pipeline > 0)

        polygons = None
        if compute_polygons:
            polygons = self._generate_polygons(image, mask_pipeline)

        return {
            "type":        "pipeline",
            "mask_binary": mask_pipeline,
            "rgba_mask":   rgba_mask,
            "polygons":    polygons,
            "image_ref":   image
        }

    def generate_polygons(self, image: np.ndarray, mask_binary: np.ndarray) -> dict:
        polygons = None
        if mask_binary is not None:
            polygons = self._generate_polygons(image, mask_binary)

        return {
            "type":      "polygons_only",
            "polygons":  polygons,
            "image_ref": image
        }

    @staticmethod
    def _render_overlay(mask: np.ndarray) -> np.ndarray:
        height, width = mask.shape
        rgba_overlay = np.zeros((height, width, 4), dtype = np.uint8)
        rgba_overlay[mask] = (0, 255, 0, 100)
        return rgba_overlay

    @staticmethod
    def _generate_polygons(image: np.ndarray, mask: np.ndarray) -> list:
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polygons = []
        for cnt in contours:
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            approx = approx.squeeze(1)
            polygons.append(approx)
        return polygons
