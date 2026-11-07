"""
====================================================

QuantEngine

Institutional Bar Series

Version 2.0

====================================================
"""

from __future__ import annotations

from core.bars.bar import Bar


class BarSeries:

    def __init__(

        self,

        max_bars: int = 5000,

    ):

        self.max_bars = max_bars

        self.bars: list[Bar] = []

    # =====================================================
    # Add
    # =====================================================

    def append(

        self,

        bar: Bar,

    ):

        self.bars.append(bar)

        if len(self.bars) > self.max_bars:

            self.bars.pop(0)

    # =====================================================
    # Clear
    # =====================================================

    def clear(self):

        self.bars.clear()

    # =====================================================
    # Basic Access
    # =====================================================

    def first(self):

        if self.bars:

            return self.bars[0]

        return None

    def last(

        self,

        n=1,

    ):

        if not self.bars:

            return None

        if n == 1:

            return self.bars[-1]

        return self.bars[-n:]

    # =====================================================
    # OHLC Arrays
    # =====================================================

    def opens(self):

        return [b.open for b in self.bars]

    def highs(self):

        return [b.high for b in self.bars]

    def lows(self):

        return [b.low for b in self.bars]

    def closes(self):

        return [b.close for b in self.bars]

    def volumes(self):

        return [b.volume for b in self.bars]

    def timestamps(self):

        return [b.timestamp for b in self.bars]

    # =====================================================
    # Python API
    # =====================================================

    def __len__(self):

        return len(self.bars)

    def __iter__(self):

        return iter(self.bars)

    def __getitem__(

        self,

        item,

    ):

        return self.bars[item]

    def __repr__(self):

        return f"BarSeries({len(self.bars)} bars)"