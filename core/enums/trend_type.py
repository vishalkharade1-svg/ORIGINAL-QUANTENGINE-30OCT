from enum import Enum


class TrendType(str, Enum):

    UNKNOWN = "UNKNOWN"

    BULLISH = "BULLISH"

    BEARISH = "BEARISH"

    RANGE = "RANGE"