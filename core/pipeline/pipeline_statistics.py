"""
====================================================

QuantEngine

Pipeline Statistics

Tracks Institutional Pipeline execution statistics.

====================================================
"""


class PipelineStatistics:

    def __init__(self):

        self.reset()

    # -------------------------------------------------

    def reset(self):

        # Pipeline

        self.processed = 0

        self.engine_calls = 0

        self.pipeline_errors = 0

        # Trading

        self.trades = 0

        self.wins = 0

        self.losses = 0

        self.breakeven = 0

        self.pnl = 0.0

    # -------------------------------------------------

    def candle(self):

        self.processed += 1

    # -------------------------------------------------

    def engine(self):

        self.engine_calls += 1

    # -------------------------------------------------

    def error(self):

        self.pipeline_errors += 1

    # -------------------------------------------------

    def trade(self, pnl):

        from core.backtesting.accounting import classify_pnl

        self.trades += 1

        self.pnl += pnl

        kind = classify_pnl(pnl)
        if kind == "WIN":
            self.wins += 1
        elif kind == "LOSS":
            self.losses += 1
        else:
            self.breakeven += 1

    # -------------------------------------------------

    @property
    def win_rate(self):

        if self.trades == 0:
            return 0.0

        return (self.wins / self.trades) * 100

    # -------------------------------------------------

    @property
    def loss_rate(self):

        if self.trades == 0:
            return 0.0

        return (self.losses / self.trades) * 100

    # -------------------------------------------------

    @property
    def average_pnl(self):

        if self.trades == 0:
            return 0.0

        return self.pnl / self.trades

    # -------------------------------------------------

    @property
    def summary(self):

        return {

            "processed_candles": self.processed,

            "engine_calls": self.engine_calls,

            "pipeline_errors": self.pipeline_errors,

            "trades": self.trades,

            "wins": self.wins,

            "losses": self.losses,

            "win_rate": self.win_rate,

            "loss_rate": self.loss_rate,

            "total_pnl": self.pnl,

            "average_pnl": self.average_pnl,

        }