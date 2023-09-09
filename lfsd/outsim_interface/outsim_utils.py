#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Project: FaSTTUBe Driverless Simulation

Description: Provides functions for decoding outsim packets
(see https://en.lfsmanual.net/wiki/InSim.txt)
"""
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple, cast

import numpy as np

from lfsd.common_types import FloatArray

HEADER_FMT = "4ciI"
MAIN_FMT = "12f3i"
INPUTS_FMT = "5f"
DRIVE_FMT = "b3x2f"
DISTANCE_FMT = "2f"
WHEEL_FMT = "7f3Bx2f"

OUTSIM_FULL_FMT = "".join(
    (HEADER_FMT, MAIN_FMT, INPUTS_FMT, DRIVE_FMT, DISTANCE_FMT, WHEEL_FMT * 4)
)

OUTSIM_FULL_STRUCT = struct.Struct(OUTSIM_FULL_FMT)

Radians = float
Ratio = float
RadiansPerSecond = float
NewtonMeters = float
Meters = float
Celsius = float
Byte = int  # in the range [0, 255]
Bar = float
MetersPerSecond = float


@dataclass
class CarInputs:
    steering: Radians
    throttle: Ratio
    brake: Ratio
    clutch: Ratio
    handbrake: Ratio


@dataclass
class CarDrive:
    gear: int
    engine_angular_velocity: RadiansPerSecond
    max_torque_at_velocity: NewtonMeters  # Nm : output torque for throttle 1.0


@dataclass
class Distance:
    current_lap_dist: Meters
    indexed_distance: Meters


@dataclass  # pylint: disable=too-many-instance-attributes
class WheelData:
    """
    The data provided by outsim regarding one wheel
    """

    suspension_deflection: float
    steer: float
    x_force: float
    y_force: float
    vertical_load: float
    angular_velocity: float
    lean_relative_to_road: float
    air_temp: Celsius
    slip_fraction: Byte
    touching_ground: int
    slip_ratio: float
    tan_slip_angle: float


@dataclass
class RawOutsimData:
    """
    A class that contains all the data provided by outsim
    """

    packet_id: int
    packet_time: int
    angular_velocity: FloatArray
    direction_global: FloatArray
    linear_acceleration_global: FloatArray
    linear_velocity_global: FloatArray
    position_global: FloatArray
    car_inputs: CarInputs
    car_drive: CarDrive
    distance: Distance
    wheels: Tuple[WheelData, WheelData, WheelData, WheelData]


def decode_full_outsim_packet(
    packet: bytes,
) -> RawOutsimData:
    """
    Decodes an extended outsim and returns relevant values, that contains wheel/tyre data etc.

    Args:
        packet (bytes): The extended outsim packet

    Returns:
       RawOutsimData: The parsed outsim data in a structured dataclass
    """

    meters_ratio = 65536

    res = cast(OUTSIM_FULL_UNPACK_TYPE, OUTSIM_FULL_STRUCT.unpack(packet))

    # header
    assert b"".join(res[:4]) == b"LFST"
    packet_id, packet_time = res[4:6]

    # main
    angular_velocity: np.ndarray = np.array(res[6:9])

    # yaw (rotated 90 to the right), pitch, roll
    direction_global: np.ndarray = np.array(res[9:12])
    # outsim heading points to the cars right, we want it to point forwards
    # so we rotate 90 deg to the left (anti-clockwise)
    direction_global[0] += np.pi / 2

    linear_acceleration_global: np.ndarray = np.array(res[12:15])
    linear_velocity_global: np.ndarray = np.array(res[15:18])
    position_global: np.ndarray = np.array(res[18:21]) / meters_ratio
    # inputs
    throttle, brake, input_steer, clutch, handbrake = res[21:26]

    # drive
    gear, engine_angular_velocity, max_torque_at_velocity = res[26:29]
    # distance
    current_lap_dist, indexed_distance = res[29:31]

    wheel1 = list(res[31:43])
    wheel1[7] = float(wheel1[7])
    wheel2 = list(res[43:55])
    wheel2[7] = float(wheel2[7])
    wheel3 = list(res[55:67])
    wheel3[7] = float(wheel3[7])
    wheel4 = list(res[67:79])
    wheel4[7] = float(wheel4[7])
    return RawOutsimData(
        packet_id,
        packet_time,
        angular_velocity,
        direction_global,
        linear_acceleration_global,
        linear_velocity_global,
        position_global,
        car_inputs=CarInputs(input_steer, throttle, brake, clutch, handbrake),
        car_drive=CarDrive(gear, engine_angular_velocity, max_torque_at_velocity),
        distance=Distance(current_lap_dist, indexed_distance),
        wheels=(
            WheelData(*wheel1),
            WheelData(*wheel2),
            WheelData(*wheel3),
            WheelData(*wheel4),
        ),
    )


OUTSIM_FULL_UNPACK_TYPE = Tuple[
    bytes,
    bytes,
    bytes,
    bytes,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    int,
    float,
    float,
]


OUTGAUGE_STRUCT = struct.Struct(
    "I"  # time
    "4s"  # car name (last byte is don't-care because of null-terminated string)
    "H"  # flags
    "2B"  # gear, player id
    "7f"  # speed, rpm, turbo pressure, engine temp, fuel, oil pressure, oil temp
    "2I"  # dash lights available, dash lights on
    "3f"  # throttle, brake, clutch
    "15sx"  # display 1 (usually fuel)
    "15sx"  # display 2 (usually settings)
)


OUTGAUGE_FULL_UNPACK_TYPE = Tuple[
    int,
    bytes,
    int,
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    int,
    int,
    float,
    float,
    float,
    bytes,
    bytes,
]


@dataclass
class RawOutgaugeData:
    time: int
    car: str
    gear: int
    speed: MetersPerSecond
    rpm: float  # rpm
    turbo_pressure: Bar  # bar
    engine_temperature: Celsius
    fuel: Ratio  # [0-1]
    oil_pressure: Bar
    oil_temperature: Celsius


def decode_outgauge_data(data: bytes) -> RawOutgaugeData:
    outgauge_pack = cast(OUTGAUGE_FULL_UNPACK_TYPE, OUTGAUGE_STRUCT.unpack(data))

    try:
        car = outgauge_pack[1].decode("utf-8")
    except UnicodeDecodeError:
        car = "mod"
    return RawOutgaugeData(
        time=outgauge_pack[0],
        car=car,
        gear=outgauge_pack[3],
        speed=outgauge_pack[5],
        rpm=outgauge_pack[6],
        turbo_pressure=outgauge_pack[7],
        engine_temperature=outgauge_pack[8],
        fuel=outgauge_pack[9],
        oil_pressure=outgauge_pack[10],
        oil_temperature=outgauge_pack[11],
    )
