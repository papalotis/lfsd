#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
This is a demo of the LFSInterface. It prints the number of visible cones and sends a steering command to LFS.
"""
import pickle
from pathlib import Path
from time import time

import typer

from lfsd import LFSInterface
from lfsd.lyt_interface.detection_model import DetectionModel
from lfsd.outsim_interface import LFSData


class SaverLFSInterface(LFSInterface):
    def __init__(
        self,
        lfs_installation_path: str | None = None,
        insim_port: int = 29999,
        virtual_joystick_port: int = 30002,
        lfs_computer_ip: str | None = None,
        detection_model: DetectionModel | None = None,
    ) -> None:
        super().__init__(
            lfs_installation_path,
            insim_port,
            virtual_joystick_port,
            lfs_computer_ip,
            detection_model,
        )

        self._data_dir: str | None
        self._buffer_size: int | None
        self._flush_interval: float | None
        self._data_buffer = []
        self._last_flush_time = time()

    async def on_lfs_data(self, data: LFSData) -> None:
        # add data to buffer
        self._data_buffer.append(data)
        # flush buffer if it's full or if it's been more than flush_interval seconds since the last flush
        if (
            len(self._data_buffer) >= self._buffer_size
            or time() - self._last_flush_time >= self._flush_interval
        ):
            self.flush_data()

    def flush_data(self):
        # create data directory if it doesn't exist
        data_path = Path(self._data_dir)

        data_path.mkdir(parents=True, exist_ok=True)

        # generate filename based on current time
        filename = f"{int(time() * 10)}.pkl"
        filepath = data_path / filename

        # early exit if buffer is empty
        if len(self._data_buffer) == 0:
            return

        # save data to file
        with open(filepath, "wb") as f:
            pickle.dump(self._data_buffer, f)

        # clear buffer and update last flush time
        self._data_buffer.clear()
        self._last_flush_time = time()

    def combine_data_files(self):
        # get list of data files
        data_path = Path(self._data_dir)
        data_files = sorted(data_path.glob("*.pkl"))

        # combine data from all files
        data_list = []
        for data_file in data_files:
            with open(data_file, "rb") as f:
                data_list.extend(pickle.load(f))

        # save combined data to file
        combined_filepath = data_path / "combined.pkl"
        with open(combined_filepath, "wb") as f:
            pickle.dump(data_list, f)

        # delete individual data files
        for data_file in data_files:
            data_file.unlink()


def main(dir_to_save: str) -> None:
    interface = SaverLFSInterface()
    interface._data_dir = dir_to_save
    interface._buffer_size = 100
    interface._flush_interval = 2.0
    try:
        interface.spin()
    except KeyboardInterrupt:
        # interface.combine_data_files()
        raise


if __name__ == "__main__":
    typer.run(main)
