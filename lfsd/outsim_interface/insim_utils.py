#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Description: Provides functions for decoding insim packets (see
https://en.lfsmanual.net/wiki/InSim.txt). We need an insim connection in order to
know the current track layout loaded.

Project: FaSTTUBe Driverless Simulation
"""

import struct
from typing import Optional, Tuple


def create_insim_initialization_packet(program_name: str, password: str) -> bytes:
    """
    Create the initialization packet for insim.

    Args:
        program_name (str): The name of the program (see insim docs).
        password (str): The insim password (see insim docs).

    Returns:
        bytes: The encoded packet.
    """
    isi = struct.pack(
        "4BHHBcH16s16s",
        44,  # Size
        1,  # Type
        1,  # ReqI
        0,  # Zero
        0,  # UDPPort
        0,  # Flags
        0,  # Sp0
        b" ",  # Prefix
        0,  # Interval
        password.encode(),  # Admin
        program_name.encode(),  # IName
    )

    return isi


def handle_insim_packet(packet: bytes) -> tuple[bytes | None, str | None]:
    """
    Handle an insim packet. It only handles the minimum number of packets that we
    need. This is not an full insim client.

    Args:
        packet: The packet to handle.

    Returns:
        The response packet, if it is required. The name of the loaded track, if it is available.
    """
    # Some constants.
    isp_tiny = 3
    isp_axi = 43  # autocross information
    isp_rst = 17  # race start
    tiny_none = 0

    packet_type = packet[1]

    # Check the packet type.
    if packet_type == isp_tiny:
        # Unpack the packet data.
        tiny = struct.unpack("BBBB", packet)
        # Check the SubT.
        if tiny[3] == tiny_none:
            return packet, None

    elif packet_type == isp_axi:
        name: bytes
        *_, name = struct.unpack("6BH32s", packet)
        return None, name.replace(b"\x00", b"").decode()
    elif packet_type == isp_rst:
        print("race starting")

    return None, None
