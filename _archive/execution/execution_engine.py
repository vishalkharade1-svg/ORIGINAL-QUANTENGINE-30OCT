"""
====================================================

QuantEngine

Execution Engine

Consumes:
    context.decision

Produces:
    Orders

====================================================
"""

from core.common.base_engine import BaseEngine
from core.common.logging_config import get_logger

log = get_logger(__name__)


class ExecutionEngine(BaseEngine):

    priority = 700

    dependencies = [
        "DecisionEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

    # -------------------------------------------------

    def analyze(self, context):

        registry = context.decision

        if registry is None:
            context.execution_signal = None
            return

        setups = registry.all()

        if not setups:
            # Must explicitly clear any stale signal from a
            # previous candle -- without this, context.
            # execution_signal keeps pointing at whatever the
            # last valid setup was, and anything reading it
            # (e.g. backtesting/backtester.py's `if signal is
            # not None and current_trade is None: open_trade(...)`)
            # will keep reopening trades off that same stale
            # setup on every candle after a trade closes, since
            # it looks identical to "a fresh valid signal".
            context.execution_signal = None
            return

        best = max(
            setups,
            key=lambda s: s.score,
        )

        log.info(
            "EXECUTION SIGNAL direction=%s entry=%.2f stop=%.2f "
            "target=%.2f rr=%.2f score=%.2f",
            best.direction,
            best.entry,
            best.stop_loss,
            best.take_profit,
            best.risk_reward,
            best.score,
        )

        # PipelineContext declares `execution_signal` as the
        # field for the best-scoring accepted setup (see
        # backtesting/backtester.py, which already reads it via
        # getattr(context, "execution_signal", None)).
        context.execution_signal = best

    # -------------------------------------------------

    def reset(self):

        pass