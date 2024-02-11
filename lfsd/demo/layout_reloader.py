import random
import time

from lfsd import LFSData, LFSInterface


class LayoutReloaderInterface(LFSInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.time_last_relaod = time.time()

    async def on_lfs_data(self, data: LFSData) -> None:
        if time.time() - self.time_last_relaod > 5:
            self.time_last_relaod = time.time()
            layout_to_load = random.choice(
                [
                    layout.stem
                    for layout in self.layouts
                    if layout.name.startswith(self.active_track)
                ]
            )
            layout_to_load = layout_to_load.replace(self.active_track, "")

            print(f"Reloading layout: {layout_to_load}")
            await self.load_layout(layout_to_load)


if __name__ == "__main__":
    lfs = LayoutReloaderInterface()
    lfs.spin()
