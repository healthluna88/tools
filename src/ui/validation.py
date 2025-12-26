from __future__ import annotations

from typing import List, Sequence

import numpy as np

from core.types import ImageU8, MaskBool, EmbeddingF32, PointSAM, PolygonI32


def validate_image_u8(image: np.ndarray) -> ImageU8:
    """Validate an image array used throughout the app.

    Contract:
    - dtype: uint8
    - shape: (H, W) grayscale OR (H, W, C) with C in {3, 4}
    - contiguous: not required, but returned as a view casted to ImageU8

    Raises:
        TypeError / ValueError: if the input does not satisfy the contract.
    """
    if not isinstance(image, np.ndarray):
        raise TypeError(f"image must be a numpy.ndarray, got {type(image)!r}")
    if image.dtype != np.uint8:
        raise ValueError(f"image dtype must be uint8, got {image.dtype}")
    if image.ndim == 2:
        return image  # type: ignore[return-value]
    if image.ndim != 3:
        raise ValueError(f"image must be 2D or 3D, got ndim={image.ndim}")
    if image.shape[2] not in (3, 4):
        raise ValueError(f"image channel count must be 3 or 4, got {image.shape[2]}")
    return image  # type: ignore[return-value]


def validate_embedding_f32(embedding: np.ndarray) -> EmbeddingF32:
    """Validate an embedding array.

    This project stores embeddings as .npy. The exact shape depends on the model,
    but typical SAM embeddings are float32 and 4D (1, C, H, W).

    Contract:
    - dtype: float32
    - ndim: 4

    Raises:
        TypeError / ValueError
    """
    if not isinstance(embedding, np.ndarray):
        raise TypeError(f"embedding must be a numpy.ndarray, got {type(embedding)!r}")
    if embedding.dtype != np.float32:
        raise ValueError(f"embedding dtype must be float32, got {embedding.dtype}")
    if embedding.ndim != 4:
        raise ValueError(f"embedding must be 4D (1,C,H,W), got ndim={embedding.ndim}")
    return embedding  # type: ignore[return-value]


def validate_mask_bool(mask: np.ndarray) -> MaskBool:
    """Validate a boolean mask.

    Contract:
    - dtype: bool
    - shape: (H, W) (2D)

    Raises:
        TypeError / ValueError
    """
    if not isinstance(mask, np.ndarray):
        raise TypeError(f"mask must be a numpy.ndarray, got {type(mask)!r}")
    if mask.dtype != np.bool_:
        raise ValueError(f"mask dtype must be bool, got {mask.dtype}")
    if mask.ndim != 2:
        raise ValueError(f"mask must be 2D (H,W), got ndim={mask.ndim}")
    return mask  # type: ignore[return-value]


def validate_points(points: Sequence[PointSAM], *, width: int, height: int) -> List[PointSAM]:
    """Validate point annotations in pixel coordinates.

    Contract:
    - points: list of dicts with keys {'x','y','label'}
    - x in [0, width-1], y in [0, height-1]
    - label: int (semantic meaning decided by upstream UI; we only enforce int)

    Returns a shallow-copied list (so caller can safely hold it).

    Raises:
        ValueError / TypeError
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid image size: width={width}, height={height}")
    out: List[PointSAM] = []
    for i, p in enumerate(points):
        if not isinstance(p, dict):
            raise TypeError(f"point[{i}] must be dict, got {type(p)!r}")
        if "x" not in p or "y" not in p or "label" not in p:
            raise ValueError(f"point[{i}] missing keys: {p!r}")
        x = int(p["x"])
        y = int(p["y"])
        label = int(p["label"])
        if not (0 <= x < width) or not (0 <= y < height):
            raise ValueError(f"point[{i}] out of bounds: (x={x}, y={y}), size=({width},{height})")
        out.append({ "x": x, "y": y, "label": label })
    return out


def validate_polygons(polygons: Sequence[Sequence[Sequence[int]]], *, width: int, height: int) -> List[PolygonI32]:
    """Validate polygons in pixel coordinates.

    Contract:
    - polygons: list of contours
    - each contour: list of (x,y) points, length >= 3
    - each x,y inside image bounds

    Returns polygons as list of int32 ndarray with shape (N,2).

    Raises:
        ValueError / TypeError
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid image size: width={width}, height={height}")
    out: List[PolygonI32] = []
    for ci, contour in enumerate(polygons):
        if contour is None:
            continue
        pts = []
        for pi, pt in enumerate(contour):
            if len(pt) != 2:
                raise ValueError(f"polygon[{ci}][{pi}] must be (x,y), got {pt!r}")
            x = int(pt[0])
            y = int(pt[1])
            if not (0 <= x < width) or not (0 <= y < height):
                raise ValueError(f"polygon[{ci}][{pi}] out of bounds: (x={x},y={y}), size=({width},{height})")
            pts.append((x, y))
        if len(pts) < 3:
            continue
        arr = np.asarray(pts, dtype = np.int32)
        out.append(arr)  # type: ignore[append-type]
    return out


def points_px_to_norm(points: Sequence[PointSAM], *, width: int, height: int) -> List[dict]:
    """Convert pixel points to normalized points in [0,1] for JSON storage."""
    validated = validate_points(points, width = width, height = height)
    return [{ "x": p["x"] / width, "y": p["y"] / height, "label": p["label"] } for p in validated]


def points_norm_to_px(points_norm: Sequence[dict], *, width: int, height: int) -> List[PointSAM]:
    """Convert normalized points (as stored in JSON) back to pixel points."""
    out: List[PointSAM] = []
    for i, p in enumerate(points_norm):
        try:
            x = int(round(width * float(p["x"])))
            y = int(round(height * float(p["y"])))
            label = int(p["label"])
        except Exception as e:
            raise ValueError(f"invalid normalized point[{i}]: {p!r}") from e
        # clamp to bounds to be robust to round-off or legacy data
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        out.append({ "x": x, "y": y, "label": label })
    return validate_points(out, width = width, height = height)


def polygons_px_to_norm(polygons: Sequence[Sequence[Sequence[int]]], *, width: int, height: int) -> List[list]:

    """Convert pixel polygons to normalized for JSON."""

    if polygons:
        polys = validate_polygons(polygons, width = width, height = height)
        out: List[list] = []
        for contour in polys:
            c = [[int(x) / width, int(y) / height] for x, y in contour.tolist()]
            out.append(c)
        return out
    return []


def polygons_norm_to_px(polygons_norm: Sequence[Sequence[Sequence[float]]], *, width: int, height: int) -> List[List[List[int]]]:
    """Convert normalized polygons to pixel coordinate lists."""
    out: List[List[List[int]]] = []
    for contour in polygons_norm or []:
        c: List[List[int]] = []
        for pt in contour or []:
            if pt is None or len(pt) != 2:
                continue
            try:
                x = int(round(width * float(pt[0])))
                y = int(round(height * float(pt[1])))
            except Exception:
                continue
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
            c.append([x, y])
        if len(c) >= 3:
            out.append(c)
    # validate will also convert to ndarray; but workspace historically stores list lists, so keep list lists
    _ = validate_polygons(out, width = width, height = height)
    return out
