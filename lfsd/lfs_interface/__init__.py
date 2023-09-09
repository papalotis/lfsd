#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
The main interface to LFS
"""
import asyncio
from abc import ABC, abstractmethod

import numpy as np

from lfsd.common import is_wsl2, get_wsl2_host_ip_address

from lfsd.outsim_interface import LFSData, OutsimInterface


class LFSInterface(ABC):
    def __init__(
        self,
        lfs_installation_path: str = "/mnt/c/LFS",
        insim_port: int = 29999,
        detection_range: float = 20.0,
        detection_angle: float = 90.0,
        virtual_joystick_port: int | None = None,
        virtual_joystick_address: str | None = None,
        lfs_computer_ip: str | None = None,
    ) -> None:
        """
        The interface to LFS.

        Args:
            lfs_installation_path: The path to where LFS is installed
            insim_port: The port to which insim is bound
            detection_range: The range of the cone detection
            detection_angle: The angle of the cone detection
            virtual_joystick_port: The port to send driving commands to
            virtual_joystick_address: The address to send driving commands to
        """

        detection_angle_rad = np.deg2rad(detection_angle)

        if lfs_computer_ip is None:
            lfs_computer_ip = self.get_lfs_computer_ip_if_possible()

        self.__outsim_interface = OutsimInterface(
            vjoy_port=virtual_joystick_port,
            insim_port=insim_port,
            lfs_path=lfs_installation_path,
            sight_range=detection_range,
            sight_angle=detection_angle_rad,
            game_address=lfs_computer_ip,
        )

    def get_lfs_computer_ip_if_possible(self) -> str:
        if is_wsl2():
            return get_wsl2_host_ip_address()
        
        raise NotImplementedError("TODO: Implement this for non-WSL2")
        

    @abstractmethod
    async def on_lfs_data(self, data: LFSData) -> None:
        """
        Called when new data is received from LFS.

        Args:
            data: The data received from LFS
        """
        pass

    def send_driving_command(
        self, steering: float, throttle: float, brake: float
    ) -> None:
        """
        Sends a driving command to LFS.

        Args:
            steering: The steering value (between -1 (left), 0 (straight), 1 (right))
            throttle: The throttle value (between 0 (no throttle) and 1 (full throttle))
            brake: The brake value (between 0 (no brake) and 1 (full brake))
        """
        self.__outsim_interface.send_driving_command(steering, throttle, brake)

    def spin(self) -> None:
        async def loop_outsim() -> None:
            async with self.__outsim_interface:
                async for data in self.__outsim_interface:
                    await self.on_lfs_data(data)

        awaitable = asyncio.gather(loop_outsim(), self.__outsim_interface.spin_insim())

        loop = asyncio.get_event_loop()
        loop.run_until_complete(awaitable)
