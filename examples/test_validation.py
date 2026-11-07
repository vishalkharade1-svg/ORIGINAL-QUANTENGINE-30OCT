"""
====================================================

QuantEngine

Validation Layer Example

Run with:

    python -m examples.test_validation

Runs the canonical PAPER TRADING replay (full institutional
pipeline, no credentials) over real BTCUSDT history, then
drives the three validation tools on the exact same flow:

    1. Walk-Forward Tester  -- rolling out-of-sample windows,
       candidates picked on each train window by in-sample
       net profit.
    2. Strategy Optimizer   -- grid sweep over RISK_PER_TRADE
       (an honest strategy parameter: it genuinely resizes
       every order the RiskEngine produces), ranked by the
       shared PerformanceAnalytics report.
    3. Monte Carlo          -- bootstrap resampling of the
       full-run closed-trade PnL sequence.

Every run uses the identical institutional pipeline wiring --
the same candles, the same pipeline, the same paper ledger.

====================================================
"""

from config.settings import settings

import config.risk_settings as risk_settings

from data.historical_loader import HistoricalLoader

from data.candle_builder import CandleBuilder

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext

from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus


from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)

from core.validation.walk_forward import WalkForwardTester

from core.validation.optimizer import StrategyOptimizer

from core.validation.monte_carlo import MonteCarloSimulator


def make_runner(symbol):
    """Canonical replay of a candle window through the full
    institutional pipeline + paper ledger. `params` carries
    one honest strategy knob: the fraction of equity risked
    per trade, read by the RiskEngine."""

    def run_window(bars, params=None):
        cfg = params or {}
        risk_per_trade = float(
            cfg.get("risk_per_trade", risk_settings.RISK_PER_TRADE)
        )

        previous = risk_settings.RISK_PER_TRADE

        risk_settings.RISK_PER_TRADE = risk_per_trade

        try:

            context = PipelineContext()

            context.market = MarketState(symbol=symbol)

            bus = EventBus()

            pipeline = InstitutionalPipeline(context)

            
            paper = PaperTradingEngine(pipeline, bus)

            for candle in bars:
                paper.run_candle(candle)

            return paper.account, paper.trades

        finally:

            risk_settings.RISK_PER_TRADE = previous

    return run_window


def main():

    symbol = settings.SYMBOLS[0]

    loader = HistoricalLoader()

    candles = loader.candles(symbol)

    builder = CandleBuilder()

    builder.load_history(list(reversed(candles["result"])))

    history = builder.history

    loader.close()

    runner = make_runner(symbol)

    print("\n" + "=" * 60)
    print("1. WALK-FORWARD TESTING")
    print("=" * 60)
    print(f"Symbol : {symbol}")
    print(f"Bars   : {len(history)}")

    wf = WalkForwardTester(
        runner=runner,
        history=history,
        train_size=300,
        test_size=100,
        candidates=[
            {"risk_per_trade": 0.005},
            {"risk_per_trade": 0.01},
            {"risk_per_trade": 0.02},
        ],
    ).run()

    for fold in wf.folds:
        print(
            f"  Fold {fold.index}  train{fold.train_range} "
            f"test{fold.test_range}  "
            f"best={fold.best_config}  "
            f"oos_trades={fold.oos_trades}  "
            f"oos_pnl={fold.oos_net_profit:+.2f}"
        )

    print(
        f"  TOTAL oos       : {wf.total_trades} trades, "
        f"net {wf.net_profit:+.2f}"
    )

    print("\n" + "=" * 60)
    print("2. STRATEGY OPTIMIZER")
    print("=" * 60)

    grid = {"risk_per_trade": [0.005, 0.01, 0.02, 0.03]}

    results = StrategyOptimizer(
        runner=runner,
        grid=grid,
    ).run(history)

    print(f"  {'risk':>8} {'pnl':>10} {'sharpe':>8} "
          f"{'trades':>6} {'dd':>10} {'win%':>7}")

    for run in results:
        print(
            f"  {run.params['risk_per_trade']:>8.3f} "
            f"{run.net_profit:>+10.2f} "
            f"{run.sharpe:>8.3f} "
            f"{run.total_trades:>6} "
            f"{run.max_drawdown:>10.2f} "
            f"{run.win_rate:>7.1f}"
        )

    print("\n" + "=" * 60)
    print("3. MONTE CARLO")
    print("=" * 60)

    best_params = results[0].params

    _, full_trades = runner(history, best_params)

    mc = MonteCarloSimulator(
        full_trades,
        starting_balance=risk_settings.STARTING_BALANCE,
    ).run(simulations=1000, seed=42)

    print(mc.summary(label="MONTE CARLO -- FULL RUN"))

    print()


if __name__ == "__main__":
    main()