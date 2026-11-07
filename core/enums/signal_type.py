from enum import Enum


class SignalType(str, Enum):

    BUY = "BUY"

    SELL = "SELL"

    EXIT = "EXIT"

    HOLD = "HOLD"