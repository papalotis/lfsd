#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
This is a demo of the LFSInterface. It prints the number of visible cones and sends a steering command to LFS.
"""
from time import time

import numpy as np

from lfsd import ConeTypes, LFSInterface


class PrinterLFSInterface(LFSInterface):
    async def on_lfs_data(self, data):
        yellow_cones = [
            cone
            for cone in data.processed_outsim_data.visible_cones
            if cone.cone_type == ConeTypes.YELLOW
        ]
        blue_cones = [
            cone
            for cone in data.processed_outsim_data.visible_cones
            if cone.cone_type == ConeTypes.BLUE
        ]

        print(f"No of yellow cones: {len(yellow_cones)}")
        print(f"No of blue cones: {len(blue_cones)}")

        steering = np.sin(time() * np.pi * 2 / 2)
        throttle = 0.5
        brake = 0.0
        await self.send_driving_command(steering, throttle, brake)


if __name__ == "__main__":
    interface = PrinterLFSInterface()

    interface.spin()
