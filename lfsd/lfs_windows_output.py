"""
Relay the desired steering, throttle and brake values to a VJoy device
"""
import math
import socket
import struct
import sys
import time
from collections import deque
from itertools import count
from typing import cast

import pyvjoy


def linearly_interpolate(
    to_map: float, start1: float, stop1: float, start2: float, stop2: float
) -> float:
    """
    Linearly maps a values `ns` with range `[start1-stop1]` to the range `[start2-stop2]`

    Args:
        to_map (float): The value to be mapped
        start1 (float): The start of the original space
        stop1 (float): The end of the original space
        start2 (float): The start of the new space
        stop2 (float): The end of the new space

    Returns:
        float: The mapped value
    """
    return (to_map - start1) / (stop1 - start1) * (stop2 - start2) + start2


JOYSTICK_SOCKET = 30002


def decode_packet(
    packet: bytes,
) -> tuple[float, float, float, float, int, float, float]:
    """
    Decodes a packet containing steering, throttle and brake information

    Args:
        packet: The packet to decode

    Returns:
        The steering, throttle brake, clutch percentages as floats and the gear change as int
    """
    fmt = "4fid3f"
    values = cast(
        tuple[float, float, float, float, int, float, float, float, float],
        struct.unpack(fmt, packet),
    )

    return values


def map_to_axis(val: float, min_val: float, max_val: float) -> int:
    """
    Maps a value so that it matches the range of a VJoy axis

    Args:
        val (float): The value to map
        min_val (float): The min value
        max_val (float): The max value

    Returns:
        int: The mapped VJoy value
    """
    return int(linearly_interpolate(val, min_val, max_val, 0, 0x8000))


def linearly_combine_values_over_time(
    tee: float, delta_time: float, previous_value: float, new_value: float
) -> float:
    """
    Linear combination of two values over time
    (see https://de.wikipedia.org/wiki/PT1-Glied)
    Args:
        tee (float): The parameter selecting how much we keep from the previous value
        and how much we update from the new
        delta_time (float): The time difference between the previous and new value
        previous_value (Numeric): The previous value
        new_value (Numeric): The next value

    Returns:
        The combined value
    """
    tee_star = 1 / (tee / delta_time + 1)
    combined_value = tee_star * (new_value - previous_value) + previous_value
    return combined_value


def main() -> None:
    """
    The main loop, connects to VJoy and waits for incoming packets, when they come they are executed as soon as possible
    """
    # raise an error if there are more than 2 arguments
    if len(sys.argv) > 2:
        raise ValueError("Too many arguments, at most 1 is allowed")

    # if there is 1 argument then it is the port
    if len(sys.argv) == 2:
        joystick_socket = int(sys.argv[1])
        assert 0 < joystick_socket < 65535, "The port must be between 0 and 65535"
    else:
        joystick_socket = JOYSTICK_SOCKET

    delays: deque[float] = deque(maxlen=100)

    try:
        j = pyvjoy.VJoyDevice(1)

        receive_time = time.time()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("0.0.0.0", joystick_socket))
            sock.settimeout(1.0)

            current_steering, current_throttle, current_brake = [0] * 3

            for _ in count():
                # Receive data.
                try:
                    data = sock.recv(384)
                except socket.timeout:
                    print("waiting for data")

                    time.sleep(1.5)
                    continue

                prev_receive_time = receive_time
                receive_time = time.time()

                delta_receive_time = receive_time - prev_receive_time

                if not data:
                    break

                (
                    steering,
                    throttle,
                    brake,
                    clutch,
                    gear_delta,
                    time_send,
                    tee_steering,
                    tee_throttle,
                    tee_brake,
                ) = decode_packet(data)

                current_steering = linearly_combine_values_over_time(
                    tee_steering, delta_receive_time, current_steering, steering
                )

                current_throttle = linearly_combine_values_over_time(
                    tee_throttle, delta_receive_time, current_throttle, throttle
                )

                current_brake = linearly_combine_values_over_time(
                    tee_brake, delta_receive_time, current_brake, brake
                )

                diff = receive_time - time_send

                delays.append(diff)

                mean_diff = math.mean(delays)
                mean_diff_ms = mean_diff * 1000
                print(f"Mean delay: {mean_diff_ms:.1f}ms")

                steering_axis_val = map_to_axis(current_steering, -1, 1)
                throttle_axis_val = map_to_axis(current_throttle, 0, 1)
                brake_axis_val = map_to_axis(current_brake, 0, 1)
                clutch_axis_val = map_to_axis(clutch, 0, 1)

                j.set_axis(pyvjoy.HID_USAGE_X, steering_axis_val)
                j.set_axis(pyvjoy.HID_USAGE_Y, throttle_axis_val)
                j.set_axis(pyvjoy.HID_USAGE_Z, brake_axis_val)
                j.set_axis(pyvjoy.HID_USAGE_RX, clutch_axis_val)

                shift_up_button = 2
                shift_down_button = 1
                j.set_button(shift_up_button, gear_delta > 0)
                j.set_button(shift_down_button, gear_delta < 0)

    finally:
        j.reset()


if __name__ == "__main__":
    main()
