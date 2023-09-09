#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Interact with live data coming from LFS outsim and outgauge ports, as well as insim (to get the current track).
"""
from __future__ import annotations

import asyncio as aio
import socket
import struct
from asyncio.streams import StreamReader, StreamWriter
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from time import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import asyncio_dgram
import numpy as np
import rclpy
from asyncio_dgram.aio import DatagramServer

from lfsd.common import (  # pylint: disable=unused-import
    get_lfs_cfg_txt_path,
    get_machine_ip_address,
    is_wsl2,
)
from lfsd.lyt_interface import LYTInterface
from lfsd.outsim_interface.functional import ProcessedOutsimData, process_outsim_data
from lfsd.outsim_interface.insim_utils import (
    create_insim_initialization_packet,
    handle_insim_packet,
)
from lfsd.outsim_interface.outsim_utils import (
    RawOutgaugeData,
    RawOutsimData,
    decode_full_outsim_packet,
    decode_outgauge_data,
)


@dataclass
class LFSData:
    """
    Represents the data that has been extracted out of the LFS sim and that now can be
    used for other applications
    """

    delta_t: float
    raw_outsim_data: RawOutsimData
    raw_outgauge_data: RawOutgaugeData
    processed_outsim_data: ProcessedOutsimData


class OutsimInterface:
    """
    Class that binds to the outsim port and publishes the parsed data in a loop
    """

    def __init__(
        self,
        vjoy_port: int,
        insim_port: int,
        lfs_path: str,
        sight_range: float,
        sight_angle: float,
        game_address: str,
    ) -> None:
        """
        Constructor for the outsim interface.

        Args:
            vjoy_port: The port that the vjoy interface is listening on.
            insim_port: The port that the insim interface is sending data to.
            lfs_path: The path to the directory where LFS is installed.
            sight_range: The range of the sensor sight.
            sight_angle: The fov angle of the sensor sight.
            game_address: The address of the machine in which LFS is running.
        """
        self.outsim_port: int
        self.outsim_asocket: DatagramServer
        self.outgauge_port: int
        self.outgauge_asocket: DatagramServer

        self.vjoy_port = vjoy_port
        self.vjoy_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.insim_port = insim_port
        self.game_address = game_address

        lfs_path = lfs_path.strip()
        self.lfs_path = Path(lfs_path)
        assert self.lfs_path.is_dir(), self.lfs_path
        self.lyt_path = self.lfs_path / "data" / "layout"
        assert self.lyt_path.is_dir(), self.lyt_path
        self.active_layout_name: str | None = None

        self.sight_range = sight_range
        self.sight_angle = sight_angle

        self.lyt_interface: LYTInterface | None = None

        self.check_lfs_cfg_and_load_ports()

    def load_cfg_outsim_outgauge(self) -> dict[str, dict[str, str]]:
        """
        Load the LFS configuration file and parse the outsim and outgauge ports. All
        strings are converted to lowercase.
        """
        cfg_path = self.lfs_path / "cfg.txt"
        assert cfg_path.is_file()

        dictionaries: dict[str, dict[str, str]] = {
            "outsim": {},
            "outgauge": {},
        }

        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            line_lower = line.lower()
            if line_lower.startswith(("outsim", "outgauge")):
                channel, setting, value = line_lower.split()
                dictionaries[channel][setting] = value

        return dictionaries

    def check_lfs_cfg_and_load_ports(self) -> None:
        """
        Check if the LFS configuration is correct.
        """

        configuration_mapping = self.load_cfg_outsim_outgauge()
        assert (
            configuration_mapping["outsim"]["mode"] == "1"
        ), "OutSim mode must be set to 1."

        assert (
            configuration_mapping["outgauge"]["mode"] == "1"
        ), "OutGauge mode must be set to 1."

        assert (
            configuration_mapping["outsim"]["opts"] == "ff"
        ), 'OutSim opts be set to "ff"'

        outsim_port = int(configuration_mapping["outsim"]["port"])
        outgauge_port = int(configuration_mapping["outgauge"]["port"])

        all_ports = [outsim_port, outgauge_port, self.insim_port, self.vjoy_port]
        names = ["outsim", "outgauge", "insim", "vjoy"]
        all_ports_set = set(all_ports) - set([0])

        ports_string = "\n".join(
            f"{name}: {port}" for port, name in zip(all_ports, names)
        )

        assert len(all_ports_set) == len(all_ports), (
            "All ports must be unique and no port can be set to 0.\n" + ports_string
        )

        outsim_send_ip = configuration_mapping["outsim"]["ip"]
        outgauge_send_ip = configuration_mapping["outgauge"]["ip"]
        if outsim_send_ip != outgauge_send_ip:
            raise ValueError(
                "The outsim and outgauge IP addresses must be the same.\n"
                f"outsim: {outsim_send_ip}\n"
                f"outgauge: {outgauge_send_ip}"
            )

        if is_wsl2():
            wsl2_machine_ip = get_machine_ip_address()
            if outsim_send_ip != wsl2_machine_ip:
                rclpy.logwarn(
                    "It looks like you are running on WSL2. You need to set the outsim"
                    " and outgauge IP addresses (%s) to the same as the WSL2 IP address (%s): %s",
                    outsim_send_ip,
                    wsl2_machine_ip,
                    get_lfs_cfg_txt_path(),
                )

        self.outsim_port = outsim_port
        self.outgauge_port = outgauge_port

    def reload_lyt_interface(self) -> None:
        """
        Load the lyt interface if the layout is known.
        """
        if self.active_layout_name is None:
            return

        layout_file_path = (self.lyt_path / self.active_layout_name).with_suffix(".lyt")
        # print(f"Loading LYT file: {layout_file_path}", flush=True)
        assert layout_file_path.is_file(), layout_file_path
        self.lyt_interface = LYTInterface(
            lyt_path=layout_file_path,
            sight_range=self.sight_range,
            sight_angle=self.sight_angle,
        )
        # print("LYT file loaded.")

    async def __aenter__(self) -> OutsimInterface:
        """Connect to outsim with udp and wait for the layout to be loaded"""

        self.outsim_asocket = await asyncio_dgram.bind(  # type: ignore
            (
                "0.0.0.0",
                self.outsim_port,
            )
        )
        self.outgauge_asocket = await asyncio_dgram.bind(  # type: ignore
            ("0.0.0.0", self.outgauge_port)
        )

        # wait until a layout file is loaded
        for i in count(start=1):
            if self.lyt_interface is not None:
                break

            if i % 10 == 0:
                print("Waiting for LYT to be loaded...")

            await aio.sleep(1)

        return self

    async def connect_to_insim(
        self, retry_every_n_seconds: int
    ) -> Tuple[StreamReader, StreamWriter, bytes]:
        """
        Try to connect to LFS insim using TCP. An infinite loop is started that
        tries to connect to the insim port every n seconds.

        Args:
            retry_every_n_seconds: The number of seconds to wait before retrying.

        Returns:
            The reader, writer and a buffer to use for storing further incoming data
            from insim.
        """
        print(
            f"Attempting to connect to insim...\nConnecting to port: {self.insim_port}"
        )

        for connection_attempt in count(start=1):
            try:
                print(self.game_address)
                reader, writer = await aio.open_connection(
                    self.game_address, self.insim_port
                )
            except ConnectionRefusedError:
                print(
                    f"Failed attempt ({connection_attempt}) to connect to insim. "
                    f"Retrying in {retry_every_n_seconds} seconds..."
                )
                print(
                    "Cannot connect to insim port. Please start LFS and initialize insim"
                    f" with the command '/insim {self.insim_port}'"
                )
                await aio.sleep(retry_every_n_seconds)
            else:
                break

        print("Connection to insim was successful.", flush=True)

        # send initialization packet
        initialization_packet = create_insim_initialization_packet("lfsd", "")
        writer.write(initialization_packet)
        await writer.drain()

        # send packet requesting the name of the active layout
        buffer_to_send_for_axi_request = bytes([4, 3, 1, 20])
        writer.write(buffer_to_send_for_axi_request)
        await writer.drain()

        new_buffer = b""

        return reader, writer, new_buffer

    def handle_insim_buffer(self, buffer: bytes, writer: StreamWriter) -> bytes:
        """
        Work with the data already received from insim. The buffer is iterated
        and every packet that is found is handled by the `handle_insim_packet` method.

        Args:
            buffer: The buffer containing incoming insim data.
            writer: The writer to use for sending data to insim. Mainly needed to
            send keepalive packets.

        Returns:
            The remaining buffer to be processed, containing incomplete data.
        """
        # Loop through each completed packet in the buffer. The first byte of
        # each packet is the packet size, so check that the length of the
        # buffer is at least the size of the first packet.
        while len(buffer) > 0 and len(buffer) > buffer[0]:
            # Copy the packet from the buffer.
            packet = buffer[: buffer[0]]

            # Remove the packet from the buffer.
            buffer = buffer[buffer[0] :]

            # The packet is now complete! :)
            to_send, layout = handle_insim_packet(packet)
            if to_send is not None:
                writer.write(to_send)
            if layout is not None and layout != self.active_layout_name:
                self.active_layout_name = layout
                self.reload_lyt_interface()

        return buffer

    async def spin_insim(self) -> None:
        """
        Get the insim data and update the current track
        """
        retry_every_n_seconds = 5
        reader, writer, buffer = await self.connect_to_insim(retry_every_n_seconds)

        for _ in count():
            data = await reader.read(1024)
            # Append received data onto the buffer.
            buffer += data
            buffer = self.handle_insim_buffer(buffer, writer)

            # When we receive an empty string that means the connection has been
            # closed.
            if len(data) == 0:
                writer.close()
                await writer.wait_closed()

                print("Connection reset from LFS insim. Will attempt to reconnect...")
                reader, writer, buffer = await self.connect_to_insim(
                    retry_every_n_seconds
                )

    async def __aexit__(self, *args: Any, **kwargs: Any) -> Any:
        """Disconnect from outsim"""
        self.outsim_asocket.close()
        self.outgauge_asocket.close()
        return False

    async def __aiter__(self) -> AsyncIterator[LFSData]:
        """
        Receive outsim and outgauge parse the incoming bytes and return a dataclass
        with all the values

        Returns:
            An async iterable

        Yields:
            LFSData: The parsed data as a dataclass
        """
        delta_ts: List[float] = []

        time_before = time()

        previous_angular_velocity = np.array([0, 0, 0])

        outsim_bytes: bytes

        for i in count():
            (outsim_bytes, _), (outgauge_bytes, _) = await aio.gather(
                self.outsim_asocket.recv(), self.outgauge_asocket.recv()
            )

            raw_outsim_data = decode_full_outsim_packet(outsim_bytes)

            raw_outgauge_data = decode_outgauge_data(outgauge_bytes)

            time_after = time()
            delta_t = time_after - time_before

            # in case the simulation is paused we don't want to
            # use the real world delta_t, instead we get the average
            # of the last few runs, since delta_t has a very low variance (it is
            # effectively the games fps) this is a safe assumption to make
            if i > 50 and len(delta_ts) > 0 and delta_t > 3 * np.mean(delta_ts):
                delta_t = np.mean(delta_ts)

            delta_ts = delta_ts[-30:] + [delta_t]

            assert self.lyt_interface is not None

            processed_outsim_data = process_outsim_data(
                delta_t, self.lyt_interface, previous_angular_velocity, raw_outsim_data
            )

            time_before, previous_angular_velocity = (
                time_after,
                raw_outsim_data.angular_velocity,
            )

            data = LFSData(
                delta_t=delta_t,
                raw_outsim_data=raw_outsim_data,
                processed_outsim_data=processed_outsim_data,
                raw_outgauge_data=raw_outgauge_data,
            )

            yield data

    def send_outputs(
        self,
        steering_percentage: float,
        throttle_percentage: float,
        brake_percentage: float,
        clutch_percentage: float,
        gear_delta: int,
    ) -> None:
        """
        Send the outputs to the vjoy port

        Args:
            steering_percentage: The percentage of the steering (-1 full left, 0 center,
            1 full right)
            throttle_percentage: The percentage of the throttle (0 no throttle,
            1 full forward)
            brake_percentage: The percentage of the brake (0 no brake, 1 full brake)
            clutch_percentage: The percentage of the clutch (0 no clutch, 1 full clutch)
            gear_delta: The gear delta (-1 downshift, 0 neutral, 1 upshift)
        """
        fmt = "4fi"
        packet = struct.pack(
            fmt,
            steering_percentage,
            throttle_percentage,
            brake_percentage,
            clutch_percentage,
            gear_delta,
        )
        self.vjoy_socket.sendto(packet, (self.game_address, self.vjoy_port))

    @classmethod
    def create_default_kwargs(cls, **update_kwargs: Any) -> dict[str, Any]:
        """
        Create the default kwargs for the outsim interface. The default values
        the perception sensor range and fov to maximum.

        Args:
            **update_kwargs (Any): Any additional kwargs to update the default kwargs with.

        Returns:
            The default kwargs that can be used to create an outsim interface using **kwargs.
        """
        update_kwargs = update_kwargs.copy()

        lfs_path = "/mnt/c/LFS/"

        # very large range
        sight_range = 1e6
        # very large angle
        sight_angle = np.deg2rad(360).item()

        outsim_interface_kwargs: dict[str, float | int | str] = dict(
            lfs_path=lfs_path,
            vjoy_port=30_002,
            insim_port=29_999,
            sight_range=sight_range,
            sight_angle=sight_angle,
            game_address="localhost",
        )
        outsim_interface_kwargs.update(update_kwargs)

        return outsim_interface_kwargs
