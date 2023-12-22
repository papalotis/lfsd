import asyncio
import json
import sys
from dataclasses import asdict
from typing import Any, Coroutine, cast

import asyncio_dgram
import numpy as np
import typer

from lfsd import LFSData, LFSInterface
from lfsd.lyt_interface.detection_model import DetectionModel


class NumpyEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that converts NumPy arrays to lists
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class PropagatorLFSInterface(LFSInterface):
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

        self._data_to_send_outside: LFSData | None = None

        self._send_host: str | None = None
        self._send_port: int | None = None
        self._recv_host: str | None = None
        self._recv_port: int | None = None

        self._send_sock: asyncio_dgram.DatagramClient | None = None
        self._recv_sock: asyncio_dgram.DatagramServer | None = None

    async def on_lfs_data(self, data):
        self._data_to_send_outside = data

    def additional_spinners(self) -> list[Coroutine[Any, Any, Any]]:
        return_value = super().additional_spinners() + [
            self.spin_send_lfs_data(),
            self.spin_recv_driving_command(),
        ]
        return return_value

    async def spin_send_lfs_data(self) -> None:
        # create socket
        self._send_sock = await asyncio_dgram.connect(
            (self._send_host, self._send_port)
        )
        while True:
            await asyncio.sleep(0.001)
            if self._data_to_send_outside is not None:
                send_dict = asdict(self._data_to_send_outside)
                send_json = json.dumps(send_dict, cls=NumpyEncoder).encode() + b"\n"

                try:
                    await self._send_sock.send(send_json)
                except ConnectionRefusedError:
                    pass

                self._data_to_send_outside = None

    async def wait_for_hosts_and_ports_to_be_set(self) -> None:
        while (
            self._send_host is None
            and self._send_port is None
            and self._recv_host is None
            and self._recv_port is None
        ):
            await asyncio.sleep(1.0)

    def parse_driving_command_buffer(
        self, buffer: bytes
    ) -> tuple[bytes, list[tuple[float, float, float, float, int]]]:
        # each command is a json list of 3 or 5 floats
        # each command is separated by a \n byte
        commands = []
        while b"\n" in buffer:
            command, buffer = buffer.split(b"\n", 1)
            try:
                command = json.loads(command.decode())
            except json.JSONDecodeError:
                # it is possible that the very first command
                # is not a complete command, so we ignore it
                pass
            else:
                if len(command) == 3:
                    steering, throttle, brake = cast(
                        tuple[float, float, float], command
                    )
                    clutch = 0.0
                    gear = 0
                elif len(command) == 5:
                    steering, throttle, brake, clutch, gear = cast(
                        tuple[float, float, float, float, int], command
                    )
                else:
                    raise ValueError(
                        f"Expected 3 or 5 driving outputs, got {len(command)}"
                    )

                commands.append((steering, throttle, brake, clutch, gear))

        return buffer, commands

    async def spin_recv_driving_command(self) -> None:
        await self.wait_for_hosts_and_ports_to_be_set()
        # create socket
        self._recv_sock = await asyncio_dgram.bind((self._recv_host, self._recv_port))

        buffer = b""
        while True:
            # receive data with timeout of 5ms
            try:
                data, addr = await asyncio.wait_for(
                    self._recv_sock.recv(), timeout=0.005
                )
            except asyncio.TimeoutError:
                continue
            else:
                buffer += data
                # parse buffer
                buffer, commands = self.parse_driving_command_buffer(buffer)

                # send the last command
                if len(commands) > 0:
                    steering, throttle, brake, clutch, gear = commands[-1]
                    await self.send_driving_command(
                        steering, throttle, brake, clutch, gear
                    )


def main(send_host: str, send_port: int, recv_host: str, recv_port: int) -> None:
    interface = PropagatorLFSInterface()

    interface._send_host = send_host
    interface._send_port = send_port
    interface._recv_host = recv_host
    interface._recv_port = recv_port

    interface.spin()


if __name__ == "__main__":
    typer.run(main)
