#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Description: Based on https://www.lfs.net/programmer/lyt
Load the cones from a lyt file.
"""

from pathlib import Path
from typing import cast

import numpy as np

from lfsd.common_types import FloatArray
from lfsd.lyt_interface.cone_observation import ConeTypes
from lfsd.lyt_interface.io.common import (
    BLOCK_STRUCT,
    HEADER_STRUCT,
    LytObjectIndexToConeType,
)


def split_header_blocks(data: bytes) -> tuple[bytes, bytes]:
    """
    Split the content of the lyt file into header and block. This split is easy because
    the header has a fixed size

    Args:
        data: The content of the lyt file

    Returns:
        The header and the block
    """
    return data[: HEADER_STRUCT.size], data[HEADER_STRUCT.size :]


def verify_lyt_header(header_data: bytes) -> None:
    """
    Parse the header and perform some sanity checks suggested by the LFS documentation

    Args:
        header_data: The header bytes of the `.lyt` file
    """

    header = cast(
        tuple[bytes, int, int, int, int, int], HEADER_STRUCT.unpack(header_data)
    )

    file_type, version, revision, _, _, _ = header
    assert file_type == b"LFSLYT"
    assert version <= 0, version
    # revision allowed up to 252
    # https://www.lfs.net/forum/thread/96153-LYT-revision-252-in-W-patch
    assert revision <= 252, revision


def extract_cone_lists(blocks_data: bytes) -> list[list[tuple[float, float]]]:
    """
    Extract the cone object positions from the object blocks bytes of a lyt file

    Args:
        blocks_data (bytes): The data in the lyt file that is not the header

    Returns:
        The cone positions split by cone type
    """
    decoded_blocks = BLOCK_STRUCT.iter_unpack(blocks_data)
    all_cones_per_type: list[list[tuple[float, float]]] = [[] for _ in ConeTypes]

    # cone_info:
    for cone_info in decoded_blocks:
        obj_x, obj_y, _, _, lyt_obj_idx, _ = cast(
            tuple[int, int, int, int, int, int], cone_info
        )

        try:
            cone_type = LytObjectIndexToConeType[lyt_obj_idx]
        except KeyError:
            # not a cone
            continue

        # the stored x,y pos is multiplied by
        # 16 in the file so we need to convert it back
        # (and cast to a float by using real div)
        obj_x_meters = obj_x / 16
        obj_y_meters = obj_y / 16
        all_cones_per_type[cone_type].append((obj_x_meters, obj_y_meters))
    return all_cones_per_type


def load_lyt_file(filename: Path | str) -> list[FloatArray]:
    """
    Load a `.lyt` file and return the positions of the cone objects inside it split
    according to `ConeTypes`

    Args:
        filename (Path): The path to the `.lyt` file

    Returns:
        List[np.ndarray]: A list of 2d np.ndarrays representing the cone positions of
        for all cone types
    """
    if isinstance(filename, str):
        filename = Path(filename)
    assert filename.is_file(), filename
    assert filename.suffix == ".lyt", filename
    data = filename.read_bytes()
    header_data, blocks_data = split_header_blocks(data)
    verify_lyt_header(header_data)

    all_cones_per_type = extract_cone_lists(blocks_data)

    all_cones_per_type_arrays = [
        np.array(cone_list).reshape(-1, 2) for cone_list in all_cones_per_type
    ]

    return all_cones_per_type_arrays
