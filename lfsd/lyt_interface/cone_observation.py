#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Define dataclasses and enums that describe a cone.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ConeTypes(IntEnum):
    """
    Enum for all possible cone types
    Taken from https://github.com/papalotis/ft-fsd-path-planning/
    """

    UNKNOWN = 0
    RIGHT = YELLOW = 1
    LEFT = BLUE = 2
    START_FINISH_AREA = ORANGE_SMALL = 3
    START_FINISH_LINE = ORANGE_BIG = 4


@dataclass
class ObservedCone:
    """
    A class that represents a single cone that has been observed
    """

    x: float
    y: float
    cone_type: ConeTypes
