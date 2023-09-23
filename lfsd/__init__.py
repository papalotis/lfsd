"""An Live for Speed interface for Formula Student Driverless"""

# import uvloop only when not running on Windows
import platform

from lfsd.lfs_interface import LFSInterface
from lfsd.lyt_interface.cone_observation import ConeTypes, ObservedCone
from lfsd.outsim_interface import LFSData

if platform.system() != "Windows":
    try:
        import uvloop
    except ImportError:
        print('You can improve performance by installing "uvloop"')
    else:
        pass
        uvloop.install()

__version__ = "0.1.1"


__all__ = ["LFSInterface", "ConeTypes", "ObservedCone", "LFSData"]
