from __future__ import annotations

import logging

import numpy as np
from PIL import ExifTags, Image

logger = logging.getLogger(__name__)

try:
    from PySide6.QtGui import QImage, QImageReader  # type: ignore
except Exception:  # pragma: no cover
    QImage = None  # type: ignore
    QImageReader = None  # type: ignore

# Pillow 的 EXIF orientation tag（如果存在）
_EXIF_ORIENTATION_TAG = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)


def correct_exif_orientation(image: Image.Image) -> Image.Image:
    """根据 EXIF Orientation 纠正图像方向（若无 EXIF 或无 Orientation，则原样返回）。"""
    try:
        exif = image.getexif()
        if not exif or _EXIF_ORIENTATION_TAG is None:
            return image

        orientation = exif.get(_EXIF_ORIENTATION_TAG)
        if orientation in (None, 1):
            return image

        if orientation == 2:
            return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if orientation == 3:
            return image.rotate(180, expand = True)
        if orientation == 4:
            return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if orientation == 5:
            return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).rotate(90, expand = True)
        if orientation == 6:
            return image.rotate(270, expand = True)
        if orientation == 7:
            return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).rotate(90, expand = True)
        if orientation == 8:
            return image.rotate(90, expand = True)

        return image
    except Exception:
        logger.exception("Failed to correct EXIF orientation")
        return image


def load_image_pil(path: str) -> np.ndarray:
    image = Image.open(path)
    image = correct_exif_orientation(image)
    return np.array(image)


def load_image_qt(path: str) -> "QImage":
    if QImageReader is None:
        raise RuntimeError("PySide6 is not available: QImageReader is None")
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    return reader.read()


def ndarray_to_qimage(image: np.ndarray) -> "QImage":
    if QImage is None:
        raise RuntimeError("PySide6 is not available: QImage is None")

    image = np.ascontiguousarray(image).astype(np.uint8, copy = False)

    if image.ndim == 2:
        h, w = image.shape
        bytes_per_line = w
        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8).copy()

    h, w, c = image.shape

    if c == 3:
        # 如果看起来像 BGR，则转为 RGB
        if image[..., 0].mean() < image[..., 2].mean():
            image = image[..., ::-1]
        bytes_per_line = w * 3
        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    if c == 4:
        bytes_per_line = w * 4
        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888).copy()

    raise ValueError(f"Unsupported ndarray shape: {image.shape}")


def roi_with_margin(mask: np.ndarray, margin: int) -> tuple[int, int, int, int]:
    height, width = mask.shape
    if not mask.any():
        raise ValueError("mask contains no positive pixels")

    ys, xs = np.where(mask)
    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()

    x_min = max(0, x_min - margin)
    x_max = min(width - 1, x_max + margin)
    y_min = max(0, y_min - margin)
    y_max = min(height - 1, y_max + margin)

    return x_min, x_max, y_min, y_max
