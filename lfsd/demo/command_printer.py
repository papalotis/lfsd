from lfsd import LFSData, LFSInterface


class CommandPrinterLFSInterface(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._last_sim_time: int | None = None

        self.register_command_callback(self.command_printer)

    async def command_printer(self, command: str) -> None:
        print(f"Got the following command from LFS: {command!r}")

    async def on_lfs_data(self, data: LFSData) -> None:
        return


if __name__ == "__main__":
    interface = CommandPrinterLFSInterface()
    interface.spin()
