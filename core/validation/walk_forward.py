"""
====================================================

QuantEngine

Walk-Forward Tester

Rolling out-of-sample evaluation over the canonical
Backtester. The history is carved into sequential folds;
each fold trains on its window (optionally choosing the best
parameterization from `candidates` by an in-sample metric)
and then validates THAT configuration on the immediately
following, never-seen test window.

The `runner` is any callable with the shape

    runner(bars, config=None) -> (account, trades)

exactly like the canonical flow (engine.run(slice) over the
shared Account + TradeRegistry). No engine state is shared
across folds -- each fold runs a fresh engine, so the
out-of-sample numbers are real, not look-ahead smoothed.

Metrics are read off the shared PerformanceAnalytics report.

====================================================
"""

from dataclasses import dataclass, field

from core.analytics.performance import (
    PerformanceAnalytics,
)


@dataclass(slots=True)
class WalkForwardFold:

    index: int

    train_range: tuple

    test_range: tuple

    best_config: object = None

    in_sample: object = None

    out_of_sample: object = None

    oos_net_profit: float = 0.0

    oos_trades: int = 0

    oos_sharpe: float = 0.0


@dataclass(slots=True)
class WalkForwardResult:

    folds: list = field(default_factory=list)

    train_size: int = 0

    test_size: int = 0

    total_trades: int = 0

    net_profit: float = 0.0

    @property
    def fold_count(self):
        return len(self.folds)

    def metrics(self):
        return {
            "fold_count": self.fold_count,
            "train_size": self.train_size,
            "test_size": self.test_size,
            "total_oos_trades": self.total_trades,
            "net_oos_profit": self.net_profit,
        }


class WalkForwardTester:

    METRICS = ("net_profit", "sharpe")

    def __init__(
        self,
        runner,
        history,
        train_size,
        test_size,
        step=None,
        candidates=None,
        metric="net_profit",
    ):

        if train_size <= 0 or test_size <= 0:
            raise ValueError(
                "WalkForwardTester: train_size and test_size "
                "must be positive."
            )

        if metric not in self.METRICS:
            raise ValueError(
                f"WalkForwardTester: unknown metric {metric!r}; "
                f"choose from {self.METRICS}."
            )

        self.runner = runner

        self.history = list(history)

        self.train_size = int(train_size)

        self.test_size = int(test_size)

        self.step = (
            int(step) if step is not None else self.test_size
        )

        self.candidates = list(candidates) if candidates else []

        self.metric = metric

    # -------------------------------------------------

    def _score(self, account, trades):

        report = PerformanceAnalytics.analyze(account, trades)

        if self.metric == "net_profit":
            return float(report.net_profit)

        return float(report.sharpe)

    # -------------------------------------------------

    def _train(self, train_bars):

        if not self.candidates:

            account, trades = self.runner(train_bars, None)

            return None, self._score(account, trades), None

        best_config = None

        best_score = None

        best_report = None

        for config in self.candidates:

            account, trades = self.runner(train_bars, config)

            score = self._score(account, trades)

            if (
                best_score is None
                or score > best_score
            ):
                best_score = score
                best_config = config
                best_report = PerformanceAnalytics.analyze(
                    account, trades
                )

        return best_config, best_score, best_report

    # -------------------------------------------------

    def _test(self, test_bars, config):

        account, trades = self.runner(test_bars, config)

        return PerformanceAnalytics.analyze(account, trades)

    # -------------------------------------------------

    def run(self):

        folds = []

        i = 0

        total = len(self.history)

        while i + self.train_size + self.test_size <= total:

            train_bars = self.history[i:i + self.train_size]

            test_bars = self.history[
                i + self.train_size:
                i + self.train_size + self.test_size
            ]

            best_config, _, in_sample = self._train(
                train_bars
            )

            out_of_sample = self._test(
                test_bars, best_config
            )

            folds.append(
                WalkForwardFold(
                    index=len(folds),
                    train_range=(i, i + self.train_size),
                    test_range=(
                        i + self.train_size,
                        i + self.train_size + self.test_size,
                    ),
                    best_config=best_config,
                    in_sample=in_sample,
                    out_of_sample=out_of_sample,
                    oos_net_profit=(
                        float(out_of_sample.net_profit)
                        if out_of_sample is not None
                        else 0.0
                    ),
                    oos_trades=(
                        int(out_of_sample.total_trades)
                        if out_of_sample is not None
                        else 0
                    ),
                    oos_sharpe=(
                        float(out_of_sample.sharpe)
                        if out_of_sample is not None
                        else 0.0
                    ),
                )
            )

            i += self.step

        result = WalkForwardResult(
            folds=folds,
            train_size=self.train_size,
            test_size=self.test_size,
        )

        result.total_trades = sum(
            fold.oos_trades for fold in folds
        )

        result.net_profit = sum(
            fold.oos_net_profit for fold in folds
        )

        return result