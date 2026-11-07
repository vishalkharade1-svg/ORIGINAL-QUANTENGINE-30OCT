"""
====================================================

Pipeline Result

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class PipelineResult:

    processed_candles: int = 0

    trade_count: int = 0

    win_rate: float = 0.0

    pnl: float = 0.0

    completed: bool = False