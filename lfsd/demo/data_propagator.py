import json
import socket
import sys
from dataclasses import asdict
from typing import Any, Coroutine

import numpy as np

from lfsd import LFSData, LFSInterface
from lfsd.lyt_interface.detection_model import DetectionModel
from lfsd.outsim_interface import LFSData


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
        lfs_installation_path: str = "/mnt/c/LFS",
        insim_port: int = 29999,
        virtual_joystick_port: int = 30002,
        lfs_computer_ip: str | None = None,
        detection_model: DetectionModel | None = None,
        host: str = "localhost",
        port: int = 9999,
    ):
        super().__init__(
            lfs_installation_path=lfs_installation_path,
            insim_port=insim_port,
            virtual_joystick_port=virtual_joystick_port,
            lfs_computer_ip=lfs_computer_ip,
            detection_model=detection_model,
        )
        self._host = host
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))

    def convert_data(self, data: LFSData) -> bytes:
        """
        Converts LFS data to a JSON-encoded byte string
        """
        data_dict = asdict(data)
        json_string = json.dumps(data_dict, cls=NumpyEncoder) + "\n"
        return json_string.encode()

    def publish_data(self, data: LFSData) -> None:
        """
        Publishes the LFS data on the TCP socket
        """
        message = self.convert_data(data)
        self._sock.sendall(message)

    def __del__(self) -> None:
        """
        Closes the socket when the object is deleted
        """
        self._sock.close()

    async def on_lfs_data(self, data: LFSData) -> None:
        return self.publish_data(data)


def main() -> None:
    host = "localhost"
    port = 9999

    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])

    interface = PropagatorLFSInterface(host=host, port=port)
    interface.spin()


if __name__ == "__main__":
    main()