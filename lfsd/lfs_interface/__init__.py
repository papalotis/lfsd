#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
The main interface to LFS
"""
import asyncio
import platform
import subprocess
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Coroutine

from lfsd.bin_interface import BinInterface
from lfsd.common import get_wsl2_host_ip_address, is_wsl2
from lfsd.common_types import FloatArray
from lfsd.lyt_interface.detection_model import (
    BasicConicalDetectionModel,
    DetectionModel,
)
from lfsd.outsim_interface import LFSData, OutsimInterface


class LFSInterface(ABC):
    def __init__(
        self,
        lfs_installation_path: str | None = None,
        insim_port: int = 29999,
        virtual_joystick_port: int = 30002,
        lfs_computer_ip: str | None = None,
        detection_model: DetectionModel | None = None,
    ) -> None:
        """
        The interface to LFS.

        Args:
            lfs_installation_path: The path to where LFS is installed. If not specified, it will use `C:\LFS` on Windows and `/mnt/c/LFS` on WSL2.
            insim_port: The port to which insim is bound
            virtual_joystick_port: The port to send driving commands to
            lfs_computer_ip: The IP address of the computer running LFS. If None, it will try to find it automatically (currently only works for WSL2). Otherwise, if not specified, it will use `127.0.0.1`.
            detection_model: The detection model to use. If not specified, it will use a detection model with practically infinite range and angle.
        """

        if detection_model is None:
            detection_model = BasicConicalDetectionModel(
                detection_range=10000.0, detection_angle=360.0
            )

        if lfs_computer_ip is None:
            lfs_computer_ip = self.__get_lfs_computer_ip_if_possible()

        if lfs_installation_path is None:
            lfs_installation_path = self.__get_default_lfs_installation_path()

        self.__outsim_interface = OutsimInterface(
            vjoy_port=virtual_joystick_port,
            insim_port=insim_port,
            lfs_path=lfs_installation_path,
            game_address=lfs_computer_ip,
            detection_model=detection_model,
        )
        self.__bin_interface = BinInterface(lfs_installation_path)

        self.__outsim_interface.register_race_start_callback(self.on_race_start)

        self.__windows_process: subprocess.Popen | None = None

    @abstractmethod
    async def on_lfs_data(self, data: LFSData) -> None:
        """
        Called when new data is received from LFS. This is the method a subclass should override to get the data from LFS and do something with it.

        Args:
            data: The data received from LFS
        """

    async def send_driving_command(
        self,
        steering: float,
        throttle: float,
        brake: float,
        clutch: float = 0.0,
        gear_delta: int = 0,
        time_: float | None = None,
    ) -> None:
        """
        Sends a driving command to LFS.

        Args:
            steering: The steering value (between -1 (left), 0 (straight), 1 (right))
            throttle: The throttle value (between 0 (no throttle) and 1 (full throttle))
            brake: The brake value (between 0 (no brake) and 1 (full brake))
            clutch: The clutch value (between 0 (no clutch) and 1 (full clutch)). Defaults to 0.0.
            gear_delta: The gear delta (between -1 (downshift) and 1 (upshift)). Defaults to 0.
            time_: The time at which the command was created.
        """
        if time_ is None:
            time_ = time.time()

        await self.__outsim_interface.send_outputs(
            steering, throttle, brake, clutch, gear_delta, time_
        )

    async def teleport_car(
        self, x: float, y: float, yaw: float, player_id: int | LFSData
    ) -> None:
        """
        Teleports the car to the specified position.

        Args:
            x: The x coordinate of the car
            y: The y coordinate of the car
            yaw: The yaw of the car
            player_id: The player ID of the car. If you don't know what this is, you probably want to use `1`. You can also pass in the `LFSData` object and it will use the player ID from there.
        """
        if isinstance(player_id, LFSData):
            player_id = player_id.raw_outgauge_data.player_id

        await self.__outsim_interface.teleport_car_to_location(x, y, yaw, player_id)

    async def toggle_lfs_pause(self) -> None:
        """
        Toggle LFS between paused and unpaused state
        """
        await self.__outsim_interface.send_press_p_command()

    @property
    def lfs_is_paused(self) -> bool:
        """
        Returns:
            bool: Whether LFS is paused or not
        """
        return self.__outsim_interface.insim_state.lfs_is_paused

    async def pause_lfs(self) -> None:
        """
        Pause LFS. If LFS is already paused, this does nothing.
        """
        if not self.lfs_is_paused:
            await self.toggle_lfs_pause()

    async def unpause_lfs(self) -> None:
        """
        Unpause LFS. If LFS is already unpaused, this does nothing.
        """
        if self.lfs_is_paused:
            await self.toggle_lfs_pause()

    @asynccontextmanager
    async def lfs_paused(self) -> AsyncGenerator[Any, Any]:
        """
        Context manager that pauses LFS while inside the context.
        """
        await self.pause_lfs()
        try:
            yield
        finally:
            await self.unpause_lfs()

    def __get_lfs_computer_ip_if_possible(self) -> str:
        if is_wsl2():
            return get_wsl2_host_ip_address()

        return "127.0.0.1"

    def __get_default_lfs_installation_path(self) -> str:
        # if windows
        if platform.system() == "Windows":
            return "C:\LFS"
        # if wsl2
        if is_wsl2():
            return "/mnt/c/LFS"

        # cannot handle other cases
        raise ValueError("Could not find default LFS installation path")

    def __start_running_windows_script_in_background(self) -> None:
        """
        Starts the script that runs LFS in the background
        """
        script_path = Path(__file__).absolute().parent.parent / "lfs_windows_output.py"
        print(f"script path: {script_path}")
        # self.__windows_process = subprocess.Popen(
        #     [
        #         "powershell.exe",
        #         "python",
        #         str(script_path),
        #         str(self.__outsim_interface.vjoy_port),
        #     ],
        #     # write output to file
        #     stdout=open("lfs_windows_output.log", "w"),
        #     stderr=subprocess.STDOUT,
        # )

    async def __loop_outsim(self) -> None:
        async with self.__outsim_interface:
            async for data in self.__outsim_interface:
                await self.on_lfs_data(data)

    def additional_spinners(self) -> list[Coroutine[Any, Any, Any]]:
        """
        Return a list of coroutines that should be run in the background, in addition to the outsim and insim spinners.
        """
        # by default, no additional spinners, subclasses can override this
        return []

    def spin(self) -> None:
        try:
            extra_spinners = self.additional_spinners()
            if len(extra_spinners) > 0:
                print(f"no of extra spinners: {len(extra_spinners)}")
            self.__start_running_windows_script_in_background()
            awaitable = asyncio.gather(
                self.__loop_outsim(),
                self.__outsim_interface.spin_outgauge_outsim_propagator_start(),
                self.__outsim_interface.spin_insim(),
                self.__outsim_interface.spin_sim_time_callbacks(),
                self.__outsim_interface.spin_check_lfs_is_running(),
                *extra_spinners,
            )

            loop = asyncio.get_event_loop()
            loop.run_until_complete(awaitable)
        except KeyboardInterrupt:
            if self.__windows_process is not None:
                # gently ask the process to stop
                self.__windows_process.terminate()
            raise

    async def on_race_start(self) -> None:
        """
        This method runs when a new LFS race starts.
        """
        pass

    @property
    def simulation_time(self) -> int:
        """
        Returns the current simulation time in seconds.
        """
        assert self.__outsim_interface is not None, "Outsim interface is not set"
        return self.__outsim_interface._simulation_time

    def register_simulation_timer_callback(
        self, callback: Callable[[], Coroutine[Any, Any, Any]], interval: int
    ) -> None:
        """
        Register a timer callback function.

        Args:
            callback: The callback function to be executed.
            interval: The interval in milliseconds at which the callback should be called.

        Returns:
            None
        """
        self.__outsim_interface.register_simulation_timer_callback(callback, interval)

    def register_command_callback(
        self, callback: Callable[[str], Coroutine[Any, Any, Any]]
    ) -> None:
        """
        Register a callback function that is called when a command is received from LFS.

        Args:
            callback: The callback function to be executed.

        Returns:
            None
        """
        self.__outsim_interface.register_command_callback(callback)

    async def send_message_to_local_user(self, message: str) -> None:
        await self.__outsim_interface.send_say_message_command(message)

    def register_autocross_object_hit_callback(
        self, callback: Callable[[], Coroutine[Any, Any, Any]]
    ) -> None:
        """
        Register a callback function that is called when an autocross object is hit.

        Args:
            callback: The callback function to be executed.

        Returns:
            None
        """
        self.__outsim_interface.register_autocross_object_hit_callback(callback)

    async def load_layout(self, layout_name: str) -> None:
        if (
            len(layout_name) > 4
            and layout_name[:2].isupper()
            and layout_name[2] == "_"
            and layout_name[3].isdigit()
        ):
            layout_name = layout_name[4:]

        await self.__outsim_interface.send_lfs_command(f"/axload {layout_name}")
        await asyncio.sleep(0.1)
        await self.__outsim_interface.send_lfs_command("/restart")

    @property
    def active_track(self) -> str | None:
        return self.__outsim_interface.active_layout_name[:4]

    @property
    def layouts(self) -> list[Path]:
        lfs_path = self.__outsim_interface.lfs_path
        layout_path = Path(lfs_path) / "data" / "layout"

        return list(layout_path.glob("*.lyt"))

    def wheel_offsets_xy(self, car_name: str) -> FloatArray:
        return self.__bin_interface.wheel_offsets_xy(car_name)
