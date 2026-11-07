"""
====================================================

QuantEngine

Build : 2.6
Module: Indicator State

Purpose:
Stores the latest values of all calculated indicators.
The Strategy Engine reads only from this module.

====================================================
"""

from dataclasses import dataclass


@dataclass
class IndicatorState:

    # Trend
    ema9: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None

    # Momentum
    rsi14: float | None = None

    # Volatility
    atr14: float | None = None

    # Trend / Momentum
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Volume
    vwap: float | None = None

    # Status
    ready: bool = False


indicator_state = IndicatorState()