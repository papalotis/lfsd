from lfsd import LFSInterface

class PrinterLFSInterface(LFSInterface):
    async def on_lfs_data(self, data):
        print(data)

if __name__ == "__main__":
    interface = PrinterLFSInterface()

    interface.spin()
