"""
Relay the desired steering, throttle and brake values to a VJoy device
"""
import socket
import struct
import sys
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


def decode_packet(packet: bytes) -> tuple[float, float, float, float, int, float]:
    """
    Decodes a packet containing steering, throttle and brake information

    Args:
        packet: The packet to decode

    Returns:
        The steering, throttle brake, clutch percentages as floats and the gear change as int
    """
    fmt = "4fid"
    values = cast(
        tuple[float, float, float, float, int, float], struct.unpack(fmt, packet)
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

    import os

    print(os.getpid())
    try:
        j = pyvjoy.VJoyDevice(1)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("0.0.0.0", joystick_socket))
            sock.settimeout(1.0)

            for _ in count():
                # Receive data.
                try:
                    data = sock.recv(384)
                except socket.timeout:
                    print("waiting for data")
                    import time

                    time.sleep(0.1)
                    continue

                receive_time = time.time()

                if not data:
                    break

                print(data)

                out = (
                    steering,
                    throttle,
                    brake,
                    clutch,
                    gear_delta,
                    time_send,
                ) = decode_packet(data)

                diff = receive_time - time_send

                print(f"diff: {diff}")

                steering_axis_val = map_to_axis(steering, -1, 1)
                throttle_axis_val = map_to_axis(throttle, 0, 1)
                brake_axis_val = map_to_axis(brake, 0, 1)
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
