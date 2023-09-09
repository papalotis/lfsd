#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Provides a class that loads a lyt file and provides observations from a given car position and angle
"""
from __future__ import annotations

from itertools import chain
from pathlib import Path

import numpy as np

from lfsd.common_types import FloatArray
from lfsd.lyt_interface.cone_observation import ConeTypes, ObservedCone
from lfsd.lyt_interface.io.load_lyt import load_lyt_file
from lfsd.math_utils import cones_in_range_and_pov_mask, trace_to_local_space


class LYTInterface:
    """
    A class that loads a lyt file and provides "visible cone" observations according to a provided
    car position and direction
    """

    def __init__(
        self,
        lyt_path: Path | str,
        sight_range: float,
        sight_angle: float,
    ) -> None:
        """
        Class that is responsible for determining which cones are visible from a given car position, direction and
        lyt file.
        Args:
            lyt_path: The path to the LYT file to use.
            sight_range: How far the car "sees" in meters
            sight_angle: The size of the fov in rad.
        """
        if isinstance(lyt_path, str):
            lyt_path = Path(lyt_path)

        self.lyt_path = lyt_path
        self.all_cones_per_type = load_lyt_file(self.lyt_path)

        self.sight_range = sight_range
        self.sight_angle = sight_angle

    def get_visible_cones(
        self, car_pos: FloatArray, car_dir: FloatArray
    ) -> list[ObservedCone]:
        """
        Returns a list of visible car cones according to their type

        Args:
            car_pos: The car's position as a 2d vector
            car_dir: The car's direction as a 2d vector

        Returns:
            All the cones that are visible from the car's pov organized by type
        """

        list_of_cones = list(
            chain.from_iterable(
                self.gather_cone_observation_single_trace(
                    cone_type,
                    car_pos,
                    car_dir,
                    trace,
                )
                for trace, cone_type in zip(self.all_cones_per_type, ConeTypes)
            )
        )

        return list_of_cones

    @classmethod
    def _create_empty_observation(cls) -> FloatArray:
        return np.zeros((0, 2))

    @classmethod
    def create_observed_cone_sequence_from_arrays(  # pylint: disable=too-many-arguments
        cls,  # pylint: disable=unused-argument
        positions: np.ndarray,
        indices: np.ndarray,
        cone_type: ConeTypes,
    ) -> list[ObservedCone]:
        """
        Creates an list of `ObservedCones` out of an array of positions, indices and the
        cone type

        Args:
            positions: The x,y positions of each cone as an (n,2) array
            indexes: The indices of each cone in the global map
            cone_type (ConeTypes): The type of the cone

        Returns:
            ObservedConeSequence: The sequence of observed cones
        """
        return [
            ObservedCone(
                x=cone_x,
                y=cone_y,
                cone_id=int(cone_id),
                cone_type=cone_type,
            )
            for (cone_x, cone_y), cone_id in zip(positions, indices)
        ]

    def gather_cone_observation_single_trace(
        self,
        cone_type: ConeTypes,
        car_pos: np.ndarray,
        car_dir: np.ndarray,
        trace: np.ndarray,
    ) -> list[ObservedCone]:
        """
        Gathers all the cones of a specific cones type that are visible from the car pov

        Args:
            cone_type: The type of cone that is being processed
            car_pos: The global position of the car
            car_dir: The direction of the car in global space
            trace: The global cone positions
        Returns:
            The cones as detected from the car pov
        """
        observed_cones_sequence: list[ObservedCone] = []
        if len(trace) == 0:
            # no cones to process, early return
            return observed_cones_sequence

        visible_mask = cones_in_range_and_pov_mask(
            car_pos, car_dir, self.sight_range, self.sight_angle, trace
        )

        if not np.any(visible_mask):
            # no visible cones, early return
            return observed_cones_sequence

        visible_cones_indices = np.nonzero(visible_mask)[0]
        visible_cones = trace[visible_mask]

        visible_local = trace_to_local_space(car_pos, car_dir, visible_cones)
        observed_cones_sequence = self.create_observed_cone_sequence_from_arrays(
            visible_local,
            visible_cones_indices,
            cone_type,
        )

        return observed_cones_sequence
