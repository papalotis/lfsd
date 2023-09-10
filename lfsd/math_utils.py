#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Project: FaSTTUBe Driverless Simulation

Description: Functions for simulating cone detection when a global map of cones and the car pose
is known
"""
from typing import Tuple

import numpy as np

from lfsd.common_types import FloatArray


def rotate(points: FloatArray, theta: float) -> FloatArray:
    """
    Rotates the points in `points` by angle `theta` around the origin

    Args:
        points: The points to rotate. Shape (n,2)
        theta: The angle by which to rotate in radians

    Returns:
        The points rotated
    """
    cos_theta, sin_theta = np.cos(theta), np.sin(theta)
    rotation_matrix = np.array(((cos_theta, -sin_theta), (sin_theta, cos_theta))).T
    return np.dot(points, rotation_matrix)


def vec_dot(vecs1: np.ndarray, vecs2: np.ndarray) -> np.ndarray:
    """
    Mutliplies vectors in an array elementwise

    Args:
        vecs1 (np.array): The first "list" of vectors
        vecs2 (np.array): The second "list" of vectors

    Returns:
        np.array: The results
    """
    return np.sum(vecs1 * vecs2, axis=-1)


def vec_angle_between(
    vecs1: np.ndarray, vecs2: np.ndarray, clip_cos_theta: bool = True
) -> np.ndarray:
    """
    Calculates the angle between the vectors of the last dimension

    Args:
        vecs1 (np.ndarray): An array of shape (...,2)
        vecs2 (np.ndarray): An array of shape (...,2)
        clip_cos_theta (bool): Clip the values of the dot products so that they are
        between -1 and 1. Defaults to True.

    Returns:
        np.ndarray: A vector, such that each element i contains the angle between
        vectors vecs1[i] and vecs2[i]
    """
    cos_theta = vec_dot(vecs1, vecs2)

    cos_theta /= np.linalg.norm(vecs1, axis=-1) * np.linalg.norm(vecs2, axis=-1)

    cos_theta = np.asarray(cos_theta)

    cos_theta_flat = cos_theta.ravel()

    if clip_cos_theta:
        cos_theta_flat[cos_theta_flat < -1] = -1
        cos_theta_flat[cos_theta_flat > 1] = 1

    return np.arccos(cos_theta)


def scramble_part(cones: np.ndarray) -> Tuple[np.ndarray, int]:
    """
    Scramles a set of cones, so that they are not in order anymore

    Args:
        cones (np.array): The cones that should be scrambled

    Returns:
        Tuple[np.array, int]: Returns a set of cones in a different order, as well as the new index of the first cone in the old set
    """
    idx = np.random.rand(len(cones)).argsort()
    random_cones = cones[idx]

    index_of_first = np.argmax(idx == 0)

    return random_cones, index_of_first


def cones_in_range_and_pov_mask(
    car_pos: np.ndarray,
    car_dir: np.ndarray,
    sight_range: float,
    sight_angle: float,
    colored_cones: np.ndarray,
) -> np.ndarray:
    """
    Calculates the indices of the visible cones according to the car position

    Args:
        car_pos (np.array): The global position of the car
        car_dir (np.array): The direction of the car in global coordinates
        sight_range (float): The max distance that a cone can be seen
        sight_angle (float): The maximum angle that a cone can have to the car and still be visible in rad
        colored_cones (np.array): The cones that define the track

    Returns:
        np.array: The indices of the visible cones
    """
    dist_from_car = np.linalg.norm(car_pos - colored_cones, axis=1)
    dist_mask = dist_from_car < sight_range

    vec_from_car = colored_cones - car_pos

    angles_to_car = vec_angle_between(car_dir[None], vec_from_car)
    mask_angles = np.logical_and(
        -sight_angle / 2 < angles_to_car, angles_to_car < sight_angle / 2
    )

    visible_cones_mask = np.logical_and(dist_mask, mask_angles)

    return visible_cones_mask


def trace_to_local_space(
    car_pos: np.ndarray, car_dir: np.ndarray, trace: np.ndarray
) -> np.ndarray:
    """
    Rotates the provided trace, so that it is not at an angle from the point of view of the car

    Args:
        car_pos (np.array): The global position of the car
        car_dir (np.array): The direction of the car
        trace (np.array): The cones that should be rotated

    Returns:
        np.array: The rotated trace from the POV of the car
    """

    car_angle = -np.arctan2(*car_dir[::-1])
    return rotate(trace - car_pos, car_angle)


def trace_to_global_space(
    car_pos: np.array, car_dir: np.array, trace: np.array
) -> np.array:
    """
    Rotates the provided trace so that it is in the correct global position

    Args:
        car_pos (np.array): The global car position
        car_dir (np.array): The direction of the car
        trace (np.array): The trace as seen by the car

    Returns:
        np.array: The position of the trace in the global space
    """
    car_angle = -np.arctan2(*car_dir[::-1])
    return rotate(trace, car_angle) + car_pos


def angle_from_2d_vector(vecs: np.ndarray) -> np.ndarray:
    """
    Calculates the angle of each vector in `vecs`. If `vecs` is just a single 2d vector
    then one angle is calculated and a scalar is returned

    >>> import numpy as np
    >>> x = np.array([[1, 0], [1, 1], [0, 1]])
    >>> angle_from_2d_vector(x)
    >>> array([0.        , 0.78539816, 1.57079633])

    Args:
        vecs (np.array): The vectors for which the angle is calculated

    Raises:
        ValueError: If `vecs` has the wrong shape a ValueError is raised

    Returns:
        np.array: The angle of each vector in `vecs`
    """
    if vecs.shape == (2,):
        return np.arctan2(vecs[1], vecs[0])
    if vecs.ndim == 2 and vecs.shape[-1] == 2:
        return np.arctan2(vecs[:, 1], vecs[:, 0])
    raise ValueError("vecs can either be a 2d vector or an array of 2d vectors")


def unit_2d_vector_from_angle(rad: np.ndarray) -> np.ndarray:
    """
    Creates unit vectors for each value in the rad array

    Args:
        rad (np.array): The angles (in radians) for which the vectors should be created

    Returns:
        np.array: The created unit vectors
    """
    rad = np.asarray(rad)
    new_shape = rad.shape + (2,)
    res = np.empty(new_shape, dtype=rad.dtype)
    res[..., 0] = np.cos(rad)
    res[..., 1] = np.sin(rad)
    return res
