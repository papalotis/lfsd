#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Common files for handling LFS LYT files
"""
from pathlib import Path
from struct import Struct
from typing import Dict

from lfsd.common import get_lfs_path
from lfsd.lyt_interface.cone_observation import ConeTypes

HEADER_STRUCT = Struct("6sBBhBB")
BLOCK_STRUCT = Struct("2h4B")

LytObjectIndexToConeType: Dict[int, ConeTypes] = {
    25: ConeTypes.UNKNOWN,
    29: ConeTypes.YELLOW,
    30: ConeTypes.YELLOW,
    23: ConeTypes.BLUE,
    24: ConeTypes.BLUE,
    27: ConeTypes.ORANGE_BIG,
    20: ConeTypes.ORANGE_SMALL,  # 20 is red but we use it to represent a small orange cone
}

ConeTypeToLytObjectIndex: Dict[ConeTypes, int] = {}
for k, v in LytObjectIndexToConeType.items():
    if v not in ConeTypeToLytObjectIndex:
        ConeTypeToLytObjectIndex[v] = k


def get_lfs_layout_path() -> Path:
    return get_lfs_path() / "data" / "layout"
