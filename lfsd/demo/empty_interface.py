from lfsd import LFSData, LFSInterface


class MyLFSInterface(LFSInterface):
    async def on_lfs_data(self, data: LFSData) -> None:
        # return
        print(data.delta_t)


if __name__ == "__main__":
    interface = MyLFSInterface()
    interface.spin()
