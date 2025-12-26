from __future__ import annotations
import numpy as np

from typing import Optional, Tuple

from numpy.typing import NDArray

from PIL import ExifTags, Image

try:
    from PySide6.QtGui import QImage, QImageReader  # type: ignore
except Exception:  # pragma: no cover
    QImage = None  # type: ignore
    QImageReader = None  # type: ignore


def correct_exif_orientation(image: Image.Image) -> Image.Image:

    try:
        exif = image.getexif()

        if not exif:

            return image

        tag = None

        for k, v in ExifTags.TAGS.items():

            if v == 'Orientation':

                tag = k

                break

        if tag is None:

            return image

        orientation = exif.get(tag, None)

        if orientation is None:

            return image

        if orientation == 1:

            return image

        elif orientation == 2:

            return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        elif orientation == 3:

            return image.rotate(180, expand = True)

        elif orientation == 4:

            return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        elif orientation == 5:

            return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).rotate(90, expand = True)

        elif orientation == 6:

            return image.rotate(270, expand = True)

        elif orientation == 7:

            return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).rotate(90, expand = True)

        elif orientation == 8:

            return image.rotate(90, expand = True)

        return image

    except Exception as e:

        print(f'Error: {e}')

        return image


def load_image_pil(path: str) -> np.ndarray:

    image = Image.open(path)
    image = correct_exif_orientation(image)

    return np.array(image)


def load_image_qt(path: str) -> QImage:

    reader = QImageReader(path)
    reader.setAutoTransform(True)

    return reader.read()


def ndarray_to_qimage(image: np.ndarray) -> QImage:

    image = np.ascontiguousarray(image).astype(np.uint8, copy = False)

    if image.ndim == 2:

        h, w = image.shape

        bytes_per_line = w

        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8).copy()

    h, w, c = image.shape

    if c == 3:

        if image[..., 0].mean() < image[..., 2].mean():  # B > R -> BGR

            image = image[..., ::-1]

        bytes_per_line = w * 3

        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    if c == 4:

        bytes_per_line = w * 4

        return QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888).copy()

    raise ValueError(f"Unsupported ndarray shape: {image.shape}")


def roi_with_margin(mask, margin):

    height, width = mask.shape

    if not mask.any():
        raise ValueError("mask contains no positive pixels")

    ys, xs = np.where(mask)

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()

    x_min = max(         0, x_min - margin)
    x_max = min(width  - 1, x_max + margin)
    y_min = max(         0, y_min - margin)
    y_max = min(height - 1, y_max + margin)

    return x_min, x_max, y_min, y_max
