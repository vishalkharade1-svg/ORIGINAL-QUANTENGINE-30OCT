from enum import Enum


class StructureType(str, Enum):

    NONE = "NONE"

    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"

    BOS = "BOS"

    CHOCH = "CHOCH"