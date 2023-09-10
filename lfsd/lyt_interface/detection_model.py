from typing import Protocol

import numpy as np

from lfsd.common_types import FloatArray, IntArray
from lfsd.math_utils import cones_in_range_and_pov_mask


class DetectionModel(Protocol):
    def detect_cones(
        self,
        vehicle_position: FloatArray,
        vehicle_direction: FloatArray,
        cone_positions: FloatArray,
        cones_types: IntArray,
    ) -> tuple[FloatArray, IntArray]:
        """
        Detects cones in the given cone positions. This method is responsible for filtering out cones that are not visible to the vehicle. Furthermore, it can add cones to the output that were not in the input. This makes it possible to create false detections. The method should return the cones in the global coordinate system.

        The method may add "phantom" cones to the output. These cones are not in the input, but are added to the output. This makes it possible to create false detections.

        The method may change the type of the cones. For example, it may change the type of a cone from `ConeTypes.BLUE` to `ConeTypes.YELLOW`. This makes it possible to create false detections. Futhermore it is possible to remove cone type information, by assigning the type `ConeTypes.UNKNOWN`.

        The cone positions may be perturbed to simulate noise in the detection process.

        Args:
            vehicle_position: The position of the vehicle
            vehicle_direction: The direction of the vehicle
            cone_positions: The positions of the cones in the global coordinate system
            cones_types: The types of the cones (same length same as `cone_positions`)

        Returns:
            A tuple of two arrays, the first is the positions of the cones that were detected (in the global frame), the second is the types of the cones that were detected. The two arrays are of the same length.
        """
        ...


class BasicConicalDetectionModel(DetectionModel):
    def __init__(self, detection_range: float, detection_angle: float) -> None:
        """
        A simple detection model that detects cones in a conical area in front of the vehicle.

        Args:
            detection_range: The range of the detection cone
            detection_angle: The angle of the detection cone in degrees
        """
        self.detection_range = detection_range

        # convert to radians
        self.detection_angle = np.deg2rad(detection_angle)

    def detect_cones(
        self,
        vehicle_position: FloatArray,
        vehicle_direction: FloatArray,
        cone_positions: FloatArray,
        cones_types: IntArray,
    ) -> tuple[FloatArray, IntArray]:
        visible_mask = cones_in_range_and_pov_mask(
            vehicle_position,
            vehicle_direction,
            self.detection_range,
            self.detection_angle,
            cone_positions,
        )

        visible_cones = cone_positions[visible_mask]

        visible_cone_types = cones_types[visible_mask]

        return visible_cones, visible_cone_types
