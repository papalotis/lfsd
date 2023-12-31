#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
This is a demo of the LFSInterface. It demonstrates the teleportation functionality.
"""
import random
from lfsd import LFSInterface


class RandomWalkLFSInterface(LFSInterface):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._teleport_every_n_data = 200
        self._counter_till_next_teleport = self._teleport_every_n_data

    async def on_lfs_data(self, data):

        self._counter_till_next_teleport -= 1
        if self._counter_till_next_teleport > 0:
            return
        
        self._counter_till_next_teleport = self._teleport_every_n_data


        position_x = data.raw_outsim_data.position_global[0]
        position_y = data.raw_outsim_data.position_global[1]
        yaw = data.raw_outsim_data.direction_global[0]

        print('Current position:', position_x, position_y, yaw)
        print()

        teleport_rage = 3.0
        new_position_x = random.uniform(-1.0, 1.0) * teleport_rage + position_x
        new_position_y = random.uniform(-1.0, 1.0) * teleport_rage + position_y
        new_yaw = random.uniform(-0.5, 0.5) + yaw

        print('Teleporting to', new_position_x, new_position_y, new_yaw)

        await self.teleport_car(new_position_x, new_position_y, new_yaw, data)


if __name__ == "__main__":
    interface = RandomWalkLFSInterface()

    interface.spin()
