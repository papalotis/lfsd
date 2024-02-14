import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


__all__ = [
    "FloatArray",
    "IntArray",
    "BoolArray",
]
