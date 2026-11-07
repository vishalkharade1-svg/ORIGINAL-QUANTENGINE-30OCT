"""
====================================================

QuantEngine

Market Event Types

====================================================
"""


class EventType:

    # -----------------------------------------
    # Market Data
    # -----------------------------------------

    CANDLE = "CANDLE"

    TRADE = "TRADE"

    TICK = "TICK"

    ORDER_BOOK = "ORDER_BOOK"

    FUNDING = "FUNDING"

    OPEN_INTEREST = "OPEN_INTEREST"

    LIQUIDATION = "LIQUIDATION"

    NEWS = "NEWS"

    SESSION_START = "SESSION_START"

    SESSION_END = "SESSION_END"

    # -----------------------------------------
    # Trading
    # -----------------------------------------

    SIGNAL = "SIGNAL"

    SETUP = "SETUP"

    DECISION = "DECISION"

    ORDER = "ORDER"

    POSITION = "POSITION"

    TRADE_CLOSED = "TRADE_CLOSED"

    # -----------------------------------------
    # System
    # -----------------------------------------

    STARTUP = "STARTUP"

    SHUTDOWN = "SHUTDOWN"

    HEARTBEAT = "HEARTBEAT"