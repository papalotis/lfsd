#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
This is a demo of the LFSInterface. It demonstrates how one can pause the game.
This is useful if one want to do computations that might not be able to run in real time.
"""
import asyncio

from lfsd import LFSData, LFSInterface


class PauseLFSInterface(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.counter = 0

    async def on_race_start(self) -> None:
        print("race started")

    async def on_lfs_data(self, data: LFSData) -> None:
        self.counter += 1
        await self.pause_lfs()
        await asyncio.sleep(0.1)
        print(self.counter)
        await self.toggle_lfs_pause()


if __name__ == "__main__":
    interface = PauseLFSInterface()

    interface.spin()