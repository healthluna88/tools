from __future__ import annotations

from typing import TypedDict, TypeAlias

import numpy as np

from numpy.typing import NDArray


class PointSAM(TypedDict):

    x:     float
    y:     float
    label: int


ImageU8:      TypeAlias = NDArray[np.uint8  ]
EmbeddingF32: TypeAlias = NDArray[np.float32]
MaskBool:     TypeAlias = NDArray[np.bool_  ]

PolygonI32: TypeAlias = NDArray[np.int32] | NDArray[np.int64]
