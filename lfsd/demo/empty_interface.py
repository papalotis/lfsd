from lfsd import LFSData, LFSInterface


class MyLFSInterface(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._last_sim_time: int | None = None

    async def on_lfs_data(self, data: LFSData) -> None:
        if self._last_sim_time is not None:
            diff = data.raw_outsim_data.packet_time - self._last_sim_time
            if diff > 10:
                print(f"Time diff: {diff}")

        self._last_sim_time = data.raw_outsim_data.packet_time


if __name__ == "__main__":
    interface = MyLFSInterface()
    interface.spin()
