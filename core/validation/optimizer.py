"""
====================================================

QuantEngine

Strategy Optimizer

Grid sweep over a strategy's parameter space. Each parameter
combination is run through the caller's runner (the canonical
Backtester flow over the shared Account + TradeRegistry), and
the results are ranked by a PerformanceAnalytics metric. The
top row is the best out-of-sample-safe configuration under the
metric, together with its full metrics dict -- no separate
state, no duplicated bookkeeping.

runner(bars, params) -> (account, trades)

The grid is the cartesian product of every value in every
parameter list, capped by max_combos to keep sweeps sane.

====================================================
"""

from dataclasses import dataclass, field
from itertools import product

from core.analytics.performance import PerformanceAnalytics


@dataclass(slots=True)
class OptimizationRun:

    params: dict

    metrics: dict

    @property
    def net_profit(self):
        return float(self.metrics.get("net_profit", 0.0))

    @property
    def sharpe(self):
        return float(self.metrics.get("sharpe", 0.0))

    @property
    def total_trades(self):
        return int(self.metrics.get("total_trades", 0))

    @property
    def max_drawdown(self):
        return float(self.metrics.get("max_drawdown", 0.0))

    @property
    def win_rate(self):
        return float(self.metrics.get("win_rate", 0.0))


class StrategyOptimizer:

    METRICS = (
        "net_profit",
        "sharpe",
        "profit_factor",
        "win_rate",
    )

    def __init__(
        self,
        runner,
        grid,
        metric="net_profit",
        max_combos=5000,
    ):

        if not isinstance(grid, dict) or not grid:
            raise ValueError(
                "StrategyOptimizer: grid must be a non-empty "
                "dict of param -> list of values."
            )

        if metric not in self.METRICS:
            raise ValueError(
                f"StrategyOptimizer: unknown metric {metric!r}; "
                f"choose from {self.METRICS}."
            )

        combos = 1

        for values in grid.values():
            combos *= max(len(values), 1)

        if combos > max_combos:
            raise ValueError(
                f"StrategyOptimizer: grid expands to {combos} "
                f"combinations (max_combos={max_combos})."
            )

        self.runner = runner

        self.grid = grid

        self.metric = metric

        self.results = []

    # -------------------------------------------------

    @property
    def best(self):
        if not self.results:
            return None
        return self.results[0]

    # -------------------------------------------------

    def run(self, history):

        keys = list(self.grid.keys())

        combos = list(product(
            *[
                self.grid[key]
                for key in keys
            ]
        ))

        self.results = []

        for combo in combos:

            params = dict(zip(keys, combo))

            account, trades = self.runner(
                list(history), params
            )

            metrics = PerformanceAnalytics.metrics(
                account, trades
            )

            self.results.append(
                OptimizationRun(
                    params=params,
                    metrics=metrics,
                )
            )

        self.results.sort(
            key=lambda run: float(
                run.metrics.get(self.metric, 0.0)
            ),
            reverse=True,
        )

        return self.results