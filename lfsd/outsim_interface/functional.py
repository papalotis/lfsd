#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Processing of outsim data
"""
from dataclasses import dataclass

import numpy as np

from lfsd.common_types import FloatArray
from lfsd.lyt_interface import LYTInterface
from lfsd.lyt_interface.cone_observation import ObservedCone
from lfsd.math_utils import unit_2d_vector_from_angle
from lfsd.outsim_interface.outsim_utils import RawOutsimData


def calc_derivative(
    delta_t: float,
    current_value: np.ndarray,
    previous_value: np.ndarray,
) -> np.ndarray:
    delta_value = current_value - previous_value
    derivative_value = delta_value / delta_t
    return derivative_value


@dataclass
class ProcessedOutsimData:
    visible_cones: list[ObservedCone]
    linear_velocity_local: np.ndarray
    linear_acceleration_local: np.ndarray
    angular_acceleration: np.ndarray


def world_to_local(
    world_vector: FloatArray, pitch: float, roll: float, yaw: float
) -> FloatArray:
    """
    Transform world_vector to local_vector using the Euler angles
    and 3D affine transformation. Uses the 3x3 matrix form because only rotation is
    required.

    Credit: https://www.lfs.net/forum/post/1961008#post1961008

    Args:
        world_vector: The world vector to be transformed
        pitch: The pitch of the car
        roll: The roll of the car
        yaw: The yaw of the car (don't forget outsim provides the heading pointing to the right, not straight ahead)

    Returns:
        The local transformed vector
    """

    sin_roll, cos_roll = np.sin(roll), np.cos(roll)
    sin_pitch, cos_pitch = np.sin(pitch), np.cos(pitch)
    sin_yaw, cos_yaw = np.sin(yaw), np.cos(yaw)

    local_vector = np.empty(3)

    # Total rotation matrix row 1 * world_vector
    local_vector[0] = (
        cos_roll * cos_yaw * world_vector[0]
        + (cos_pitch * sin_yaw + sin_pitch * sin_roll * cos_yaw) * world_vector[1]
        + (sin_pitch * sin_yaw - cos_pitch * sin_roll * cos_yaw) * world_vector[2]
    )

    # Total rotation matrix row 2 * world_vector
    local_vector[1] = (
        -cos_roll * sin_yaw * world_vector[0]
        + (cos_pitch * cos_yaw - sin_pitch * sin_roll * sin_yaw) * world_vector[1]
        + (sin_pitch * cos_yaw + cos_pitch * sin_roll * sin_yaw) * world_vector[2]
    )

    # Total rotation matrix row 3 * world_vector
    local_vector[2] = (
        sin_roll * world_vector[0]
        - sin_pitch * cos_roll * world_vector[1]
        + cos_pitch * cos_roll * world_vector[2]
    )

    return local_vector


def process_outsim_data(
    delta_t: float,
    cone_interface: LYTInterface,
    previous_angular_velocity: FloatArray,
    raw_outsim_data: RawOutsimData,
) -> ProcessedOutsimData:
    """
    Processes the outsim data. The visible cones, angular acceleration and local linear
    velocity and linear acceleration vectors are calculated.

    Args:
        delta_t: The time since the last outsim packet
        cone_interface: The lyt interface object to extract the visible cones
        previous_angular_velocity: The previous angular velocity of the car
        raw_outsim_data: The parsed outsim data

    Returns:
        The processed outsim data
    """
    yaw, pitch, roll = raw_outsim_data.direction_global

    direction_global_xy = unit_2d_vector_from_angle(yaw)
    position_global_xy = raw_outsim_data.position_global[:2]

    cone_observation = cone_interface.get_visible_cones(
        position_global_xy, direction_global_xy
    )

    angular_acceleration = calc_derivative(
        delta_t, raw_outsim_data.angular_velocity, previous_angular_velocity
    )

    linear_velocity_local = world_to_local(
        raw_outsim_data.linear_velocity_global, pitch, roll, yaw
    )

    linear_acceleration_local = world_to_local(
        raw_outsim_data.linear_acceleration_global, pitch, roll, yaw
    )

    return ProcessedOutsimData(
        visible_cones=cone_observation,
        linear_velocity_local=linear_velocity_local,
        linear_acceleration_local=linear_acceleration_local,
        angular_acceleration=angular_acceleration,
    )
