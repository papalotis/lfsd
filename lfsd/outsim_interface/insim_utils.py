#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Description: Provides functions for decoding insim packets (see
https://en.lfsmanual.net/wiki/InSim.txt).

// char			1-byte character
// byte			1-byte unsigned integer
// word			2-byte unsigned integer
// short		2-byte signed integer
// unsigned		4-byte unsigned integer
// int			4-byte signed integer
// float		4-byte float
"""

import struct

from lfsd.lyt_interface.io.write_lyt import _to_lyt_heading
import math

def create_insim_initialization_packet(program_name: str, password: str) -> bytes:
    """
    Create the initialization packet for insim.

    Args:
        program_name: The name of the program (see insim docs).
        password: The insim password (see insim docs).

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


def create_teleport_command_packet(
    x: float, y: float, yaw: float, player_id: int
) -> bytes:
    """
    // JOIN REQUEST - allows external program to decide if a player can join
    // ============

    // Set the ISF_REQ_JOIN flag in the IS_ISI to receive join requests
    // A join request is seen as an IS_NPL packet with ZERO in the NumP field
    // An immediate response (e.g. within 1 second) is required using an IS_JRR packet

    // In this case, PLID must be zero and JRRAction must be JRR_REJECT or JRR_SPAWN
    // If you allow the join and it is successful you will then get a normal IS_NPL with NumP set
    // You can also specify the start position of the car using the StartPos structure

    // IS_JRR can also be used to move an existing car to a different location
    // In this case, PLID must be set, JRRAction must be JRR_RESET or higher and StartPos must be set

    struct IS_JRR // Join Request Reply - send one of these back to LFS in response to a join request
    {
        byte	Size;		// 16
        byte	Type;		// ISP_JRR
        byte	ReqI;		// 0
        byte	PLID;		// ZERO when this is a reply to a join request - SET to move a car

        byte	UCID;		// set when this is a reply to a join request - ignored when moving a car
        byte	JRRAction;	// 1 - allow / 0 - reject (should send message to user)
        byte	Sp2;
        byte	Sp3;

        ObjectInfo	StartPos; // 0: use default start point / Flags = 0x80: set start point
    };

    // To use default start point, StartPos should be filled with zero values

    // To specify a start point, StartPos X, Y, Zbyte and Heading should be filled like an autocross
    // start position, Flags should be 0x80 and Index should be zero

    // Values for JRRAction byte

    enum
    {
        JRR_REJECT,
        JRR_SPAWN,
        JRR_2,
        JRR_3,
        JRR_RESET,
        JRR_RESET_NO_REPAIR,
        JRR_6,
        JRR_7,
    };


    struct ObjectInfo // Info about a single object - explained in the layout file format
    {
        short	X;
        short	Y;

        byte	Zbyte;
        byte	Flags;
        byte	Index;
        byte	Heading;
    };
    """
    ISP_JRR = 58
    JRR_RESET = 4

    size = 16
    type = ISP_JRR
    reqi = 0

    # this will basically always be 1 ,but since we get the info from outgauge we can use it
    plid = player_id
    ucid = 0  # don't care
    jrr_action = JRR_RESET
    sp2 = 0  # don't care
    sp3 = 0

    # check https://www.lfs.net/programmer/lyt
    x = int(x * 16)
    y = int(y * 16)
    zbyte = 240

    flags = 0x80
    index = 0

    # we divide by 2 because in lfs the heading is 0 when the car is facing the positive y axis (the heading points to the right of the car)
    heading = _to_lyt_heading(yaw - math.pi / 2, input_is_radians=True).item()

    return struct.pack(
        "BBBBBBBBhhBBBB",
        size,
        type,
        reqi,
        plid,
        ucid,
        jrr_action,
        sp2,
        sp3,
        x,
        y,
        zbyte,
        flags,
        index,
        heading,
    )


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
        pass

    return None, None
