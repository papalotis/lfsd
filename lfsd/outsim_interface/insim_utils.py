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

import math
import struct
from dataclasses import dataclass

from lfsd.lyt_interface.io.write_lyt import _to_lyt_heading


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
    type_ = ISP_JRR
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
        type_,
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


def create_press_p_command_packet() -> bytes:
    ISP_MST = 13

    size = 68
    type_ = ISP_MST
    reqi = 0
    zero = 0

    cmd = b"/press p"
    cmd = cmd.ljust(64, b"\x00")

    packet = struct.pack(
        "BBBB64s",
        size,
        type_,
        reqi,
        zero,
        cmd,
    )

    return packet


from typing_extensions import Self


@dataclass
class InSimState:
    """
    // ISS state flags

    #define ISS_GAME			1		// in game (or MPR)
    #define ISS_REPLAY			2		// in SPR
    #define ISS_PAUSED			4		// paused
    #define ISS_SHIFTU			8		// SHIFT+U mode
    #define ISS_DIALOG			16		// in a dialog
    #define ISS_SHIFTU_FOLLOW	32		// FOLLOW view
    #define ISS_SHIFTU_NO_OPT	64		// SHIFT+U buttons hidden
    #define ISS_SHOW_2D			128		// showing 2d display
    #define ISS_FRONT_END		256		// entry screen
    #define ISS_MULTI			512		// multiplayer mode
    #define ISS_MPSPEEDUP		1024	// multiplayer speedup option
    #define ISS_WINDOWED		2048	// LFS is running in a window
    #define ISS_SOUND_MUTE		4096	// sound is switched off
    #define ISS_VIEW_OVERRIDE	8192	// override user view
    #define ISS_VISIBLE			16384	// InSim buttons visible
    #define ISS_TEXT_ENTRY		32768	// in a text entry dialog
    """

    replay_speed: float
    flags: int
    in_game_cam: int
    view_plid: int
    num_p: int
    num_conns: int
    num_finished: int
    race_in_prog: int
    qual_mins: int
    race_laps: int
    server_status: int
    track: str
    weather: int
    wind: int

    @property
    def lfs_is_paused(self) -> bool:
        return bool(self.flags & 0x4)

    @classmethod
    def from_bytes(cls, packet: bytes) -> Self:
        """
        struct IS_STA // STAte
        {
            byte	Size;			// 28
            byte	Type;			// ISP_STA
            byte	ReqI;			// ReqI if replying to a request packet
            byte	Zero;

            float	ReplaySpeed;	// 4-byte float - 1.0 is normal speed

            word	Flags;			// ISS state flags (see below)
            byte	InGameCam;		// Which type of camera is selected (see below)
            byte	ViewPLID;		// Unique ID of viewed player (0 = none)

            byte	NumP;			// Number of players in race
            byte	NumConns;		// Number of connections including host
            byte	NumFinished;	// Number finished or qualified
            byte	RaceInProg;		// 0 = no race / 1 = race / 2 = qualifying

            byte	QualMins;
            byte	RaceLaps;		// see "RaceLaps" near the top of this document
            byte	Sp2;
            byte	ServerStatus;	// 0 = unknown / 1 = success / > 1 = fail

            char	Track[6];		// short name for track e.g. FE2R
            byte	Weather;		// 0,1,2...
            byte	Wind;			// 0 = off / 1 = weak / 2 = strong
        };
        """

        assert (
            len(packet) == 28
        ), f"Packet is not the correct length, expected 28, got {len(packet)}"
        data = struct.unpack(
            "".join(
                [
                    "BBBB",  # Size, Type, ReqI, Zero
                    "f",  # ReplaySpeed
                    "HBB",  # Flags, InGameCam, ViewPLID
                    "BBBB",  # NumP, NumConns, NumFinished, RaceInProg
                    "BBBB",  # QualMins, RaceLaps, Sp2, ServerStatus
                    "6sBB",  # Track, Weather, Wind
                ]
            ),
            packet,
        )
        assert isinstance(data[16], bytes)

        return InSimState(
            replay_speed=data[4],
            flags=data[5],
            in_game_cam=data[6],
            view_plid=data[7],
            num_p=data[8],
            num_conns=data[9],
            num_finished=data[10],
            race_in_prog=data[11],
            qual_mins=data[12],
            race_laps=data[13],
            server_status=data[15],
            track=data[16].decode(),
            weather=data[17],
            wind=data[18],
        )


def create_request_IS_STA_packet() -> bytes:
    ISP_TINY = 3
    TINY_SST = 7

    size = 4
    reqi = 1
    subt = TINY_SST

    return struct.pack("BBBB", size, ISP_TINY, reqi, subt)


def handle_insim_packet(
    packet: bytes,
) -> tuple[bytes | None, str | None, InSimState | None, bool]:
    """
    Handle an insim packet. It only handles the minimum number of packets that we
    need. This is not an full insim client.

    Args:
        packet: The packet to handle.

    """
    # Some constants.
    isp_tiny = 3
    isp_axi = 43  # autocross information
    isp_rst = 17  # race start
    isp_sta = 5  # state
    tiny_none = 0

    packet_type = packet[1]

    packet_to_send, name, insim_state, is_race_start = None, None, None, False

    # Check the packet type.
    if packet_type == isp_tiny:
        # Unpack the packet data.
        tiny = struct.unpack("BBBB", packet)
        # Check the SubT.
        if tiny[3] == tiny_none:
            # this is a keep alive packet we send it back to keep the connection alive
            packet_to_send = packet
    elif packet_type == isp_axi:
        name_raw: bytes
        *_, name_raw = struct.unpack("6BH32s", packet)
        name = name_raw.decode().replace("\x00", "")
    elif packet_type == isp_rst:
        is_race_start = True
    elif packet_type == isp_sta:
        insim_state = InSimState.from_bytes(packet)

    return packet_to_send, name, insim_state, is_race_start
