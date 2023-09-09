#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Description: Write lyt files for LFS
Given the cones of a track write a lyt file that can be used in LFS
"""


from typing import cast

import numpy as np

from lfsd.lyt_interface.cone_observation import ConeTypes
from lfsd.math_utils import angle_from_2d_vector
from typing_extensions import Literal

from lfsd.common_types import FloatArray
from lfsd.lyt_interface.io.common import (
    BLOCK_STRUCT,
    HEADER_STRUCT,
    ConeTypeToLytObjectIndex,
    get_lfs_layout_path,
)


def _to_lyt_heading(heading: float, input_is_radians: bool) -> np.ndarray:
    """
    Convert real world heading (direction) to lyt heading
    See Note 2 in https://www.lfs.net/programmer/lyt

    Args:
        heading: The heading in the real world
        input_is_radians: If set to True the input will be converted to degrees as required by LYT.

    Returns:
        The heading is required by LYT
    """
    if input_is_radians:
        heading = np.rad2deg(heading)
    return ((heading + 180) * 256 // 360).astype(np.uint8)


def _create_lyt_block_for_cone(
    x_pos: int, y_pos: int, heading: int, color_index: int
) -> bytes:
    z_height = 240  # suggested by documentation (puts element on ground)
    flags = 0  # these are simple cone objects no flags
    block = BLOCK_STRUCT.pack(x_pos, y_pos, z_height, flags, color_index, heading)
    return block


def _create_lyt_trace_bytes(trace: np.ndarray, color_idx: int) -> bytes:
    if len(trace) > 0:
        trace_looped = cast(np.ndarray, np.vstack((trace, trace[:1])))
        heading = angle_from_2d_vector(trace_looped[1:] - trace_looped[:-1])
        # NOTE 2 in format
        heading = _to_lyt_heading(heading, input_is_radians=True)
        all_blocks = b"".join(
            _create_lyt_block_for_cone(x, y, h, color_idx)
            for (x, y), h in zip(trace, heading)
        )
        return all_blocks
    return b""


def _create_start_block(x_pos: int, y_pos: int, heading: float) -> bytes:
    z_height = 240
    index = 0
    flags = 0  # start position has 0 width
    heading = _to_lyt_heading(heading, input_is_radians=True)
    block = BLOCK_STRUCT.pack(x_pos, y_pos, z_height, flags, index, heading)
    return block


def _create_finish_block(x_pos: int, y_pos: int, heading: float, width: float) -> bytes:
    block = bytearray(_create_start_block(x_pos, y_pos, heading))
    # width of finish object
    block[5] |= int(width / 2) << 2
    return bytes(block)


def _create_checkpoint_block(
    x_pos: int,
    y_pos: int,
    heading: float,
    width: float,
    checkpoint_index: Literal[1, 2, 3],
) -> bytes:
    if checkpoint_index not in (1, 2, 3):
        raise ValueError(
            f"checkout_index must be either 1, 2 or 3. It is {checkpoint_index}"
        )
    block = bytearray(_create_finish_block(x_pos, y_pos, heading, width))
    block[5] |= checkpoint_index
    return bytes(block)


def _traces_to_lyt_bytes(
    cones_per_type: list[FloatArray], offset_in_meters: tuple[float, float]
) -> bytes:
    lfs_scale = 16
    offset = offset_in_meters * lfs_scale

    cones_in_map = [(c * lfs_scale + offset).astype(int) for c in cones_per_type]

    cones_bytes = [
        _create_lyt_trace_bytes(cones, ConeTypeToLytObjectIndex[cone_type])
        for cone_type, cones in zip(ConeTypes, cones_in_map)
    ]

    right_in_map = cones_in_map[ConeTypes.RIGHT]
    left_in_map = cones_in_map[ConeTypes.LEFT]
    start_finish_in_map = cones_in_map[ConeTypes.START_FINISH_LINE]

    pos_x, pos_y = (left_in_map[-2] + right_in_map[-2]) // 2
    start_heading: float = (
        angle_from_2d_vector(left_in_map[-2] - left_in_map[-1]) + np.pi / 2
    )
    start_block = _create_start_block(pos_x, pos_y, start_heading)

    finish_pos_x, finish_pos_y = (start_finish_in_map[0] + start_finish_in_map[1]) // 2

    # divide by lfs_scale because we need actual width
    finish_width = 3 * (
        np.linalg.norm(start_finish_in_map[0] - start_finish_in_map[1]) / lfs_scale
    )
    finish_heading = angle_from_2d_vector(left_in_map[-1] - left_in_map[0]) + np.pi / 2
    finish_block = _create_finish_block(
        finish_pos_x, finish_pos_y, finish_heading, finish_width
    )

    # put checkpoint approximately in the middle
    # this is so that lfs counts lap times
    half_len = len(left_in_map) // 2
    left_point_half = left_in_map[half_len]
    right_point_half_index = np.linalg.norm(
        left_point_half - right_in_map, axis=1
    ).argmin(axis=0)

    right_point_half = right_in_map[right_point_half_index]
    check_pos_x, check_pos_y = (left_point_half + right_point_half) // 2
    check_width = 5 * (np.linalg.norm(left_point_half - right_point_half) / lfs_scale)
    check_heading = (
        angle_from_2d_vector(left_in_map[half_len - 1] - left_in_map[half_len])
        + np.pi / 2
    )

    check_block = _create_checkpoint_block(
        check_pos_x, check_pos_y, check_heading, check_width, 1
    )

    final_object_blocks = b"".join(
        (start_block, finish_block, check_block, *cones_bytes)
    )

    n_obj = len(final_object_blocks) // BLOCK_STRUCT.size
    assert len(final_object_blocks) % BLOCK_STRUCT.size == 0
    header = HEADER_STRUCT.pack(b"LFSLYT", 0, 251, n_obj, 10, 8)

    final_bytes = b"".join((header, final_object_blocks))
    return final_bytes


def write_traces_as_lyt(
    world_name: Literal["BL4", "AU1", "AU2", "AU3", "WE3", "LA2"],
    layout_name: str,
    cones_per_type: list[FloatArray],
) -> None:
    """
    Write the provided cones as a lyt file. The final file will be named
    <world_name>_<layout_name>

    Args:
        world_name: The world (map) to create the track in
        layout_name: The name of the layout
        cones_per_type: List of cones split by type (see `ConeTypes`)
    """

    lfs_layout_path = get_lfs_layout_path()

    try:
        # manually selected to be close to center of the map
        offset = {
            "BL4": (-261, 124),
            "AU1": (-50, -1010),
            "AU2": (-138, -696),
            "AU3": (-66, -50),
            "WE3": (64, -1200),
            "LA2": (538, 548),
        }[world_name]
    except KeyError as e:
        raise ValueError(f"Unknown world {world_name}") from e

    offset = np.array(offset)

    assert offset is not None

    bytes_to_write = _traces_to_lyt_bytes(cones_per_type, offset)

    filename = f"{world_name}_{layout_name}.lyt"
    path = lfs_layout_path / filename
    path.write_bytes(bytes_to_write)
