"""An Live for Speed interface for Formula Student Driverless"""

import platform

from lfsd.lfs_interface import LFSInterface
from lfsd.lfs_samples_dict import LFSSamplesDict
from lfsd.lyt_interface.cone_observation import ConeTypes, ObservedCone
from lfsd.outsim_interface import LFSData
from lfsd.outsim_interface.insim_utils import ObjectHitEvent

if platform.system() != "Windows":
    # import uvloop only when not running on Windows
    try:
        import uvloop
    except ImportError:
        print('You can improve performance by installing "uvloop"')
    else:
        uvloop.install()

__version__ = "0.1.4.26"


__all__ = [
    "LFSInterface",
    "ConeTypes",
    "ObservedCone",
    "LFSData",
    "LFSSamplesDict",
    "ObjectHitEvent",
]
