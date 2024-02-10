#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Interact with live data coming from LFS outsim and outgauge ports, as well as insim (to get the current track).
"""
from __future__ import annotations

import asyncio as aio
import mmap
import os
import struct
import sys
from asyncio.streams import StreamReader, StreamWriter
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from time import time
from typing import Any, AsyncIterator, Callable, Coroutine, List, Tuple

import asyncio_dgram
import numpy as np
from asyncio_dgram.aio import DatagramClient
from typing_extensions import Self

from lfsd.common import get_propagator_write_path
from lfsd.lyt_interface import LYTInterface
from lfsd.lyt_interface.detection_model import DetectionModel
from lfsd.outsim_interface.functional import ProcessedOutsimData, process_outsim_data
from lfsd.outsim_interface.insim_utils import (
    InSimState,
    create_insim_initialization_packet,
    create_key_press_command_packet,
    create_request_IS_STA_packet,
    create_say_packet,
    create_teleport_command_packet,
    handle_insim_packet,
)
from lfsd.outsim_interface.outsim_outgauge_data_propagator import (
    propagator_is_already_running,
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

    timestamp: float
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
        game_address: str,
        detection_model: DetectionModel,
    ) -> None:
        """
        Constructor for the outsim interface.

        Args:
            vjoy_port: The port that the vjoy interface is listening on.
            insim_port: The port that the insim interface is sending data to.
            lfs_path: The path to the directory where LFS is installed.
            game_address: The address of the machine in which LFS is running.
            detection_model: The detection model to use for detecting cones.
        """

        assert vjoy_port > 0, "The vjoy port must be greater than 0."
        assert insim_port > 0, "The insim port must be greater than 0."
        assert vjoy_port != insim_port, "The vjoy and insim port must be different."

        # self._outsim_outgauge_propagator_process: aio.subprocess.Process | None = None

        self.vjoy_port = vjoy_port
        self.vjoy_asocket: DatagramClient

        self._insim_reader: StreamReader | None = None
        self._insim_writer: StreamWriter | None = None

        self.insim_port = insim_port
        self.game_address = game_address

        lfs_path = lfs_path.strip()
        self.lfs_path = Path(lfs_path)
        assert self.lfs_path.is_dir(), self.lfs_path
        self.lyt_path = self.lfs_path / "data" / "layout"
        assert self.lyt_path.is_dir(), self.lyt_path
        self.active_layout_name: str | None = None

        self.__detection_model = detection_model
        self.lyt_interface: LYTInterface | None = None

        self.insim_state: InSimState | None = None
        self.race_start_callbacks: list[Callable[[], Coroutine[Any, Any, Any]]] = []

        # a list of callbacks that are called every interval milliseconds
        # each tuple represents a callback, the interval and the last time the callback
        # was called
        self.simulation_timer_callbacks: list[
            tuple[Callable[[], Coroutine[Any, Any, Any]], int, int]
        ] = []

        self._simulation_time: int | None = None

        self._command_callbacks: list[Callable[[str], Coroutine[Any, Any, Any]]] = []

        self._mmap_path = get_propagator_write_path() / "mmap_data"
        self._mmap_path.parent.mkdir(parents=True, exist_ok=True)
        self._mmap_fd = os.open(str(self._mmap_path.absolute()), os.O_RDWR)
        self._mmap = mmap.mmap(self._mmap_fd, 1024)

    async def spin_outgauge_outsim_propagator_start(self) -> None:
        process = None
        try:
            while True:
                await aio.sleep(0.1)
                if not propagator_is_already_running():
                    print("Starting propagator...")
                    path_to_script = (
                        Path(__file__).parent / "outsim_outgauge_data_propagator.py"
                    )

                    process = await aio.create_subprocess_exec("python", path_to_script)
                    # wait until the process is running
                    await aio.sleep(1.0)
        finally:
            if process is not None:
                print("Terminating propagator...")
                await aio.sleep(0.1)
                process.terminate()

    def reload_lyt_interface(self) -> None:
        """
        Load the lyt interface if the layout is known.
        """
        if self.active_layout_name is None:
            return

        layout_file_path = (self.lyt_path / self.active_layout_name).with_suffix(".lyt")
        print(f"Loading LYT file: {layout_file_path}", flush=True)
        assert layout_file_path.is_file(), layout_file_path
        self.lyt_interface = LYTInterface(
            lyt_path=layout_file_path,
            detection_model=self.__detection_model,
        )

    async def __aenter__(self) -> Self:
        """Connect to insim"""

        print(
            f"connecting to vjoy: address: {self.game_address}, port: {self.vjoy_port}"
        )
        self.vjoy_asocket = await asyncio_dgram.connect(
            (self.game_address, self.vjoy_port)
        )

        # wait until a layout file is loaded
        for i in count(start=1):
            if self.lyt_interface is not None:
                break

            if i % 10 == 0:
                print("Waiting for LYT to be loaded...")

            await aio.sleep(1)

        return self

    async def send_message_to_insim(self, packet: bytes) -> None:
        """
        Send message to InSim. Raise RuntimeError if insim is not connected.
        """
        if self._insim_writer is None:
            raise RuntimeError("InSim is not connected.")

        self._insim_writer.write(packet)
        await self._insim_writer.drain()

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
                self._insim_reader, self._insim_writer = await aio.open_connection(
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

        assert self._insim_reader is not None
        assert self._insim_writer is not None
        print("Connection to insim was successful.", flush=True)

        # send initialization packet
        # get pid to distinguish between different instances of interface
        current_pid = os.getpid()
        initialization_packet = create_insim_initialization_packet(
            f"lfsd-{current_pid}", ""
        )
        await self.send_message_to_insim(initialization_packet)

        # send packet requesting the name of the active layout
        buffer_to_send_for_axi_request = bytes([4, 3, 1, 20])
        await self.send_message_to_insim(buffer_to_send_for_axi_request)

        # send packet requesting the state of the simulation
        packet_request_is_sta = create_request_IS_STA_packet()
        await self.send_message_to_insim(packet_request_is_sta)

        new_buffer = b""

        return self._insim_reader, self._insim_writer, new_buffer

    def handle_insim_buffer(self, buffer: bytes, writer: StreamWriter) -> bytes:
        """
        Work with the data already received from insim. The buffer is iterated
        and every packet that is found is handled by the `handle_insim_packet` method.

        Args:
            buffer: The buffer containing incoming insim data.
            writer: The writer to use for sending data to insim.

        Returns:
            The remaining buffer to be processed, containing incomplete data.
        """
        # Loop through each completed packet in the buffer. The first byte of
        # each packet is the packet size, so check that the length of the
        # buffer is at least the size of the first packet.
        while len(buffer) > 0 and len(buffer) >= buffer[0]:
            # Copy the packet from the buffer.
            packet = buffer[: buffer[0]]

            # Remove the packet from the buffer.
            buffer = buffer[buffer[0] :]

            # The packet is now complete! :)
            (
                to_send,
                layout,
                new_insim_state,
                is_race_start,
                command,
            ) = handle_insim_packet(packet)
            if to_send is not None:
                writer.write(to_send)
            if layout is not None and layout != self.active_layout_name:
                self.active_layout_name = layout
                self.reload_lyt_interface()
            if new_insim_state is not None:
                self.insim_state = new_insim_state

            if is_race_start:
                for callback in self.race_start_callbacks:
                    aio.create_task(callback())

            if command is not None:
                for callback in self._command_callbacks:
                    aio.create_task(callback(command))

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
        return False

    def get_propagator_file_to_use(self) -> Path | None:
        path_to_monitor = get_propagator_write_path()
        try:
            file_to_use = max(
                path_to_monitor.iterdir(), key=lambda x: x.stat().st_mtime
            )
        except ValueError:
            file_to_use = None

        return file_to_use

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
        last_timestamp = None
        from icecream import ic

        for i in count():
            await aio.sleep(0.004)
            self._mmap.seek(0)
            data = self._mmap.read(1024)
            timestamp = data[:8]
            assert len(timestamp) == 8
            if timestamp == last_timestamp:
                continue

            last_timestamp = timestamp

            rest = data[8:]
            try:
                outgauge_bytes, outsim_bytes = rest.split(b"LFST")
            except ValueError:
                print(f"Error in data loading. Length of data is {len(data)}")
                continue
            outsim_bytes = b"LFST" + outsim_bytes
            outsim_bytes = outsim_bytes[:272]

            time_after = time()
            delta_t = time_after - time_before

            raw_outsim_data = decode_full_outsim_packet(outsim_bytes)
            self._simulation_time = raw_outsim_data.packet_time

            raw_outgauge_data = decode_outgauge_data(outgauge_bytes)

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
                timestamp=time_after,
                delta_t=delta_t,
                raw_outsim_data=raw_outsim_data,
                processed_outsim_data=processed_outsim_data,
                raw_outgauge_data=raw_outgauge_data,
            )

            yield data

    async def send_outputs(
        self,
        steering_percentage: float,
        throttle_percentage: float,
        brake_percentage: float,
        clutch_percentage: float,
        gear_delta: int,
        time_: float,
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
            time_: The time at which the command is sent (this is used to estimate the delay in the command being sent to the game and the game receiving it)
        """
        fmt = "4fif"
        packet = struct.pack(
            fmt,
            steering_percentage,
            throttle_percentage,
            brake_percentage,
            clutch_percentage,
            gear_delta,
            time_,
        )
        await self.vjoy_asocket.send(packet)

        # self.vjoy_socket.sendto(packet, (self.game_address, self.vjoy_port))

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

    async def teleport_car_to_location(
        self, x: float, y: float, yaw: float, player_id: int
    ) -> None:
        """
        Teleport the car to a specific location.

        Args:
            x: The x coordinate of the car.
            y: The y coordinate of the car.
            yaw: The yaw of the car.
            player_id: The player id of the car.
        """
        teleport_packet = create_teleport_command_packet(x, y, yaw, player_id)
        self._insim_writer.write(teleport_packet)
        await self._insim_writer.drain()

    async def send_key_press_command(self, key: str) -> None:
        """
        Send '/press `key`' command to LFS.
        """
        buffer = create_key_press_command_packet(key)
        await self.send_message_to_insim(buffer)

    async def send_press_p_command(self) -> None:
        """
        Send the press p command to LFS.
        """
        await self.send_key_press_command("p")

    async def send_say_message_command(self, message: str) -> None:
        buffer = create_say_packet(message)
        await self.send_message_to_insim(buffer)

    def register_race_start_callback(
        self, func: Callable[[], Callable[[], Coroutine[Any, Any, Any]]]
    ) -> None:
        self.race_start_callbacks.append(func)

    def register_simulation_timer_callback(
        self, func: Callable[[], Coroutine[Any, Any, Any]], interval: int
    ) -> None:
        """
        Register a callback that is every interval milliseconds. The timer that is used is the internal LFS simulation timer. The simulation timer runs with the same frequency as the frame rate of LFS and is at most 100 Hz (even if the frame rate is higher). This info is from 01.01.2024. There are plans to update the LFS engine to run at 1000 Hz, but this is not yet implemented. This means that for now any interval below 10 ms will get called every 10 ms.

        Args:
            func: The function to call every interval milliseconds.
            interval: The interval in milliseconds.
        """
        assert interval > 0, "The interval must be greater than 0."
        if interval < 10:
            print(
                "WARNING: The interval is below 10 ms. LFS runs at a maximum of 100 Hz, so the callback will be called every 10 ms.",
                file=sys.stderr,
            )

        # -1 means the callback has not been called yet
        self.simulation_timer_callbacks.append((func, interval, -1))

    def run_simulation_timer_callbacks(self) -> None:
        """
        Run the simulation timer callbacks.
        """
        if self._simulation_time is None:
            return

        next_time_callbacks: list[
            tuple[Callable[[], Coroutine[Any, Any, Any]], int, int]
        ] = []

        while len(self.simulation_timer_callbacks) > 0:
            func, interval, last_time_called = self.simulation_timer_callbacks.pop()

            # the simulation has restarted
            if self._simulation_time < last_time_called:
                last_time_called = -1

            should_call_now = (
                self._simulation_time - last_time_called > interval
                and last_time_called != -1
            )
            if should_call_now:
                aio.create_task(func())

            if should_call_now or last_time_called == -1:
                last_time_called = self._simulation_time

            next_time_callbacks.append((func, interval, last_time_called))

        self.simulation_timer_callbacks.extend(next_time_callbacks)

    async def spin_sim_time_callbacks(self) -> None:
        """
        Spin the simulation timer callbacks.
        """
        while True:
            await aio.sleep(1 / 200)
            self.run_simulation_timer_callbacks()

    async def spin_check_lfs_is_running(self) -> None:
        # run the tasklist command every 5 seconds and capture the output
        # if the output contains LFS then we know that LFS is running

        lfs_is_running = False

        while True:
            process = await aio.create_subprocess_exec(
                "tasklist.exe", stdout=aio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            stdout = stdout.decode("utf-8")

            tasks = self._parse_tasklist_output(stdout)

            if not any("LFS.exe" == task[0] for task in tasks):
                lfs_is_running = False
                print("WARNING: LFS is NOT running.")
            else:
                if not lfs_is_running:
                    print("LFS is running.")
                    lfs_is_running = True
            await aio.sleep(5)

    def _parse_tasklist_output(
        self, tasklist_output: str
    ) -> list[tuple[str, int, str, int, int]]:
        """Image Name                     PID Session Name        Session#    Mem Usage
        ========================= ======== ================ =========== ============
        System Idle Process              0 Services                   0          8 K
        System                           4 Services                   0     12.488 K"""
        lines = tasklist_output.splitlines()

        lines = lines[3:]
        lines = [line.strip() for line in lines]
        lines = [line.split("  ") for line in lines]
        lines = [[x.strip() for x in line if x != ""] for line in lines]
        lines = [
            [a, *b.split(" "), c, d.replace(" K", "").replace(".", "")]
            for a, b, c, d in lines
        ]
        lines = [
            (line[0], int(line[1]), line[2], int(line[3]), int(line[4]))
            for line in lines
        ]
        return lines

    def register_command_callback(
        self, callback: Callable[[str], Coroutine[Any, Any, Any]]
    ) -> None:
        self._command_callbacks.append(callback)
