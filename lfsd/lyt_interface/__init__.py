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
from lfsd.lyt_interface.detection_model import DetectionModel
from lfsd.lyt_interface.io.load_lyt import load_lyt_file
from lfsd.math_utils import trace_to_local_space


class LYTInterface:
    """
    A class that loads a lyt file and provides "visible cone" observations according to a provided
    car position and direction
    """

    def __init__(
        self,
        lyt_path: Path | str,
        detection_model: DetectionModel,
    ) -> None:
        """
        Class that is responsible for determining which cones are visible from a given car position, direction and
        lyt file.
        Args:
            lyt_path: The path to the LYT file to use.
            detection_model: The detection model to use. If not specified a simple conical detection model is used.
        """
        if isinstance(lyt_path, str):
            lyt_path = Path(lyt_path)

        self.lyt_path = lyt_path

        # load the lyt file
        all_cones_per_type = load_lyt_file(self.lyt_path)
        self.all_cones_positions = np.concatenate(all_cones_per_type)
        self.all_cones_types = np.array(
            list(
                chain.from_iterable([c] * len(all_cones_per_type[c]) for c in ConeTypes)
            )
        )

        self.detection_model = detection_model

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
        # run the detection model
        (
            detected_cone_positions,
            detected_cone_types,
        ) = self.detection_model.detect_cones(
            car_pos,
            car_dir,
            self.all_cones_positions,
            self.all_cones_types,
        )

        # transform to local space
        detected_cone_positions_local = trace_to_local_space(
            car_pos, car_dir, detected_cone_positions
        )

        # convert to ObservedCone list
        list_of_cones = [
            ObservedCone(x=x, y=y, cone_type=ConeTypes(cone_type))
            for (x, y), cone_type in zip(
                detected_cone_positions_local, detected_cone_types
            )
        ]

        return list_of_cones
