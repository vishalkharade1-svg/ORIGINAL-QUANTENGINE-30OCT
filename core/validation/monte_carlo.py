"""
====================================================

QuantEngine

Monte Carlo Simulator

Bootstrap resampling (with replacement) of the closed-trade
PnL sequence produced by ANY execution mode. Each simulation
resamples N trade PnLs, re-walks the equity curve from the
starting balance, and records the final equity and the
peak-to-trough drawdown of that walk. The result is the
distribution: are the observed returns robust, or a single
lucky ordering?

Deterministic when seeded: every simulation draws from
Random(seed + index), so the same seed reproduces the same
result exactly.

Input: the shared trade sequence (TradeRegistry or sequence
of Trade objects) -- open trades are excluded, matching the
analytics closed-only view.

====================================================
"""

from dataclasses import dataclass, field
import random


@dataclass(slots=True)
class MonteCarloResult:

    simulations: int = 0

    seed: int = 0

    trades_count: int = 0

    starting_balance: float = 0.0

    mean_net_profit: float = 0.0

    p50_net_profit: float = 0.0

    p25_net_profit: float = 0.0

    p95_net_profit: float = 0.0

    worst_net_profit: float = 0.0

    mean_max_drawdown: float = 0.0

    p95_max_drawdown: float = 0.0

    p95_max_drawdown_percent: float = 0.0

    survival_rate: float = 0.0

    samples: list = field(default_factory=list)

    def summary(self, label="MONTE CARLO"):
        lines = [
            "",
            "=" * 60,
            f"{label}",
            "=" * 60,
            f"Simulations      : {self.simulations}",
            f"Seed             : {self.seed}",
            f"Closed trades    : {self.trades_count}",
            f"Starting balance : {self.starting_balance:,.2f}",
            f"Mean net profit  : {self.mean_net_profit:+,.2f}",
            f"P25 / P50 / P95  : "
            f"{self.p25_net_profit:+,.2f} / "
            f"{self.p50_net_profit:+,.2f} / "
            f"{self.p95_net_profit:+,.2f}",
            f"Worst net profit : {self.worst_net_profit:+,.2f}",
            f"Mean max drawdown: {self.mean_max_drawdown:,.2f}",
            f"P95 drawdown     : "
            f"{self.p95_max_drawdown:,.2f} "
            f"({self.p95_max_drawdown_percent:.2f}%)",
            f"Survival rate    : {self.survival_rate*100:.2f}%",
        ]
        return "\n".join(lines)


class MonteCarloSimulator:

    def __init__(
        self,
        trades,
        starting_balance=0.0,
    ):

        self.starting_balance = float(starting_balance)

        self.pnls = [
            t.pnl
            for t in _closed(trades)
        ]

    # -------------------------------------------------

    def run(
        self,
        simulations=1000,
        seed=42,
    ):

        if simulations <= 0:
            raise ValueError(
                "MonteCarloSimulator: simulations must be "
                "positive."
            )

        pnls = self.pnls

        samples = []

        for sim in range(simulations):

            rng = random.Random(seed + sim)

            if not pnls:

                samples.append({
                    "net_profit": 0.0,
                    "max_drawdown": 0.0,
                    "final_equity": self.starting_balance,
                    "survived": True,
                })

                continue

            sequence = [
                rng.choice(pnls)
                for _ in range(len(pnls))
            ]

            equity = self.starting_balance

            peak = equity

            max_dd = 0.0

            survived = True

            for pnl in sequence:

                equity += pnl

                if equity <= 0:
                    survived = False

                if equity > peak:
                    peak = equity
                else:
                    dd = peak - equity
                    if dd > max_dd:
                        max_dd = dd

            net_profit = equity - self.starting_balance

            samples.append({
                "net_profit": net_profit,
                "max_drawdown": max_dd,
                "final_equity": equity,
                "survived": survived,
            })

        profits = sorted(s["net_profit"] for s in samples)

        drawdowns = sorted(s["max_drawdown"] for s in samples)

        result = MonteCarloResult(
            simulations=simulations,
            seed=seed,
            trades_count=len(pnls),
            starting_balance=self.starting_balance,
            mean_net_profit=_mean(profits),
            p50_net_profit=_percentile(profits, 50),
            p25_net_profit=_percentile(profits, 25),
            p95_net_profit=_percentile(profits, 95),
            worst_net_profit=(
                profits[0] if profits else 0.0
            ),
            mean_max_drawdown=_mean(drawdowns),
            p95_max_drawdown=_percentile(drawdowns, 95),
            survival_rate=(
                sum(1 for s in samples if s["survived"])
                / simulations
                if simulations
                else 0.0
            ),
            samples=samples,
        )

        result.p95_max_drawdown_percent = (
            (
                result.p95_max_drawdown
                / result.starting_balance
                * 100.0
            )
            if result.starting_balance > 0
            else 0.0
        )

        return result


def _closed(trades):
    from core.backtesting.trade_registry import TradeRegistry

    if isinstance(trades, TradeRegistry):
        raw = trades.all()
    else:
        raw = list(trades or [])

    return [
        t for t in raw
        if getattr(t, "status", "") == "CLOSED"
    ]


def _mean(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(sorted_values, q):
    if not sorted_values:
        return 0.0
    index = round(q / 100.0 * (len(sorted_values) - 1))
    return float(sorted_values[index])