from lfsd import LFSData, LFSInterface


class TimerLFSInterface(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.register_simulation_timer_callback(self.every_100_ms, 100)
        self.register_simulation_timer_callback(self.every_1000_ms, 1000)
        self.register_simulation_timer_callback(self.every_1_ms, 1)
        self.register_simulation_timer_callback(self.every_20_s, 20 * 1000)

    async def every_20_s(self) -> None:
        """
        Called every 20 s.
        """
        print("20 s")

    async def every_100_ms(self) -> None:
        """
        Called every 100 ms.
        """
        # print("100 ms")

    async def every_1000_ms(self) -> None:
        """
        Called every 1000 ms.
        """
        # print("1000 ms")

    async def every_1_ms(self) -> None:
        """
        Called every 1 ms.
        """
        # print("1 ms")

    async def on_lfs_data(self, data: LFSData) -> None:
        pass


if __name__ == "__main__":
    lfs = TimerLFSInterface()
    lfs.spin()
