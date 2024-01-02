"""
Binds to the Outsim and Outgauge ports and propagates data to other programs that receive the data from this program. This program is never started from the command line. It is started the Outsim Interface module.
"""
from __future__ import annotations

import asyncio
import sys
import time
from itertools import count
from pathlib import Path

import aiofiles
import asyncio_dgram

from lfsd.common import (
    get_lfs_cfg_txt_path,
    get_lfs_path,
    get_machine_ip_address,
    get_propagator_write_path,
    is_wsl2,
)


class OutsimOutgaugeDataPropagator:
    def __init__(self) -> None:
        self._outsim_server: asyncio_dgram.DatagramServer | None = None
        self._outgauge_server: asyncio_dgram.DatagramServer | None = None

        self.outsim_port: int | None = None
        self.outgauge_port: int | None = None

        self.check_lfs_cfg_and_load_ports()

        self._propagator_write_path = get_propagator_write_path()

    async def __aenter__(self) -> OutsimOutgaugeDataPropagator:
        self._outsim_server = await asyncio_dgram.bind(  # type: ignore
            ("0.0.0.0", self.outsim_port)
        )

        self._outgauge_server = await asyncio_dgram.bind(  # type: ignore
            ("0.0.0.0", self.outgauge_port)
        )

        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        if self._outsim_server is not None:
            self._outsim_server.close()

        if self._outgauge_server is not None:
            self._outgauge_server.close()

    async def spin(self) -> None:
        """
        Spin forever, propagating data from the Outsim and Outgauge ports to the propagator file.
        """
        assert self._outsim_server is not None
        assert self._outgauge_server is not None

        for i in count():
            outsim_data, _ = await self._outsim_server.recv()
            outgauge_data, _ = await self._outgauge_server.recv()

            # if i % 100 == 0:
            #     print(f"Received {i} packets.")

            combined = outgauge_data + outsim_data

            counter = i % 200
            file_to_write = self._propagator_write_path / f"{counter:03}.pickle"
            file_to_write.parent.mkdir(parents=True, exist_ok=True)
            file_to_write.write_bytes(combined)

    def load_cfg_outsim_outgauge(self) -> dict[str, dict[str, str]]:
        """
        Load the LFS configuration file and parse the outsim and outgauge ports. All
        strings are converted to lowercase.
        """
        cfg_path = get_lfs_path() / "cfg.txt"
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

        all_ports = [outsim_port, outgauge_port]
        names = ["outsim", "outgauge"]
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
                print(
                    f"It looks like you are running on WSL2. You need to set the outsim"
                    f" and outgauge IP addresses ({outsim_send_ip}) to the same as the WSL2 IP address ({wsl2_machine_ip}): {get_lfs_cfg_txt_path()}",
                    file=sys.stderr,
                )

        self.outsim_port = outsim_port
        self.outgauge_port = outgauge_port


LOCK_FILE = Path("/tmp/lfsd/outsim_outgauge_data_propagator.lock")


async def spin_update_lock_file() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch()

    to_write = True

    async with aiofiles.open(LOCK_FILE, "w") as lock_file:
        while True:
            await asyncio.sleep(1)
            await lock_file.seek(0)
            await lock_file.write("1" if to_write else "0")
            await lock_file.flush()
            to_write = not to_write


async def spin_outsim_outgauge() -> None:
    async with OutsimOutgaugeDataPropagator() as propagator:
        await propagator.spin()


def propagator_is_already_running() -> bool:
    """
    Check if the propagator is already running.
    """
    # check when the lock file was last modified. if it was modified in the last 5 seconds, then we assume that the propagator is already running
    return LOCK_FILE.is_file() and time.time() - LOCK_FILE.stat().st_mtime < 5


async def amain() -> None:
    if propagator_is_already_running():
        print("The propagator is already running. Exiting.")
        return

    try:
        await asyncio.gather(
            spin_outsim_outgauge(),
            spin_update_lock_file(),
        )
    finally:
        LOCK_FILE.unlink()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
