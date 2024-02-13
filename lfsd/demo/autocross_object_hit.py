from rich import print

from lfsd import LFSData, LFSInterface


class AutocrossObjectHit(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.register_autocross_object_hit_callback(self.object_hit)

    async def on_lfs_data(self, data: LFSData) -> None:
        pass

    async def object_hit(self, obj) -> None:
        """
        This method runs when an autocross object is hit.
        """
        print(obj)


if __name__ == "__main__":
    lfs = AutocrossObjectHit()
    lfs.spin()
