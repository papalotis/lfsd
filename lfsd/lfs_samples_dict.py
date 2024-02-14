from typing import TypedDict

from lfsd.outsim_interface import LFSData
from lfsd.outsim_interface.insim_utils import ObjectHitEvent


class LFSSamplesDict(TypedDict):
    lfs_data: list[LFSData]
    object_hit_events: list[ObjectHitEvent]


__all__ = ["LFSSamplesDict"]
