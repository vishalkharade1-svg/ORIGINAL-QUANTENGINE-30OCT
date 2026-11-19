"""Opt-in quality-gated adapters for paper entry points (Phase 206).

The legacy PaperTradingEngine and VerifiedPaperRuntime implementations are
kept byte-for-byte stable because their source files participate in frozen
strategy/provenance guards. These wrappers add a fail-closed intake boundary
without changing those frozen implementations or any live sink.

Use GatedPaperTradingEngine in place of PaperTradingEngine when constructing a
paper strategy engine, or GatedVerifiedPaperRuntime for the verified feed's
in-memory paper sink. The existing PaperRuntime gate remains available through
its own market_data_max_age_seconds configuration.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Callable, Iterable

from core.exchanges.paper_data_quality_gate import (
    PaperDataGateDecision,
    evaluate_paper_candle,
)
from core.paper_trading.paper_trading_engine import PaperTradingEngine
from core.runtime.verified_runtime import VerifiedPaperRuntime


def _evaluate(candle: Any, *, now: datetime | Callable[[], datetime], expected_symbol: str | None,
              max_age_seconds: float, source: str) -> PaperDataGateDecision:
    try:
        current = now() if callable(now) else now
        return evaluate_paper_candle(
            candle,
            now=current,
            expected_symbol=expected_symbol,
            max_age_seconds=max_age_seconds,
        )
    except Exception:
        # Do not leak payloads or exception details into logs/reports.
        return PaperDataGateDecision(
            False, ("MARKET_DATA_GATE_ERROR",),
            getattr(candle, "symbol", None), source,
        )


class GatedPaperTradingEngine(PaperTradingEngine):
    """PaperTradingEngine variant that rejects bad candles before any work."""

    def __init__(self, *args, market_data_max_age_seconds: float,
                 market_data_expected_symbol: str | None = None,
                 market_data_now_provider: Callable[[], datetime] | None = None,
                 **kwargs):
        if (market_data_max_age_seconds is None
                or not math.isfinite(float(market_data_max_age_seconds))
                or float(market_data_max_age_seconds) < 0):
            raise ValueError("market_data_max_age_seconds must be finite and non-negative")
        self.market_data_max_age_seconds = float(market_data_max_age_seconds)
        self.market_data_expected_symbol = market_data_expected_symbol
        self.market_data_now_provider = market_data_now_provider or (
            lambda: datetime.now(timezone.utc)
        )
        self.market_data_gate_decisions: list[PaperDataGateDecision] = []
        self.rejected_market_data_candles = 0
        super().__init__(*args, **kwargs)

    def run_candle(self, candle):
        context = getattr(self.pipeline, "context", None)
        market = getattr(context, "market", None)
        expected_symbol = (
            self.market_data_expected_symbol
            or getattr(market, "symbol", None)
            or getattr(candle, "symbol", None)
        )
        decision = _evaluate(
            candle,
            now=self.market_data_now_provider,
            expected_symbol=expected_symbol,
            max_age_seconds=self.market_data_max_age_seconds,
            source="gated-paper-trading-engine",
        )
        self.market_data_gate_decisions.append(decision)
        if not decision.accepted:
            self.rejected_market_data_candles += 1
            return False
        super().run_candle(candle)
        return True


class GatedVerifiedPaperRuntime(VerifiedPaperRuntime):
    """Verified feed runtime with a quality gate before the paper sink."""

    def __init__(self, symbols: Iterable[str], *,
                 market_data_max_age_seconds: float,
                 market_data_now_provider: Callable[[], datetime] | None = None,
                 **kwargs):
        if (market_data_max_age_seconds is None
                or not math.isfinite(float(market_data_max_age_seconds))
                or float(market_data_max_age_seconds) < 0):
            raise ValueError("market_data_max_age_seconds must be finite and non-negative")
        self.market_data_max_age_seconds = float(market_data_max_age_seconds)
        self.market_data_now_provider = market_data_now_provider or (
            lambda: datetime.now(timezone.utc)
        )
        self.market_data_gate_decisions: list[PaperDataGateDecision] = []
        self.rejected_market_data_candles = 0
        super().__init__(symbols, **kwargs)

    def _on_verified_candle(self, candle) -> None:
        if candle.symbol not in self.symbols:
            decision = PaperDataGateDecision(
                False, ("SYMBOL_MISMATCH",), getattr(candle, "symbol", None),
                "gated-verified-paper-runtime",
            )
        else:
            decision = _evaluate(
                candle,
                now=self.market_data_now_provider,
                expected_symbol=candle.symbol,
                max_age_seconds=self.market_data_max_age_seconds,
                source="gated-verified-paper-runtime",
            )
        self.market_data_gate_decisions.append(decision)
        if not decision.accepted:
            self.rejected_market_data_candles += 1
            return
        self.paper_sink(candle)

    def stats(self) -> dict[str, Any]:
        result = super().stats()
        result.update({
            "market_data_gate_enabled": True,
            "rejected_market_data_candles": self.rejected_market_data_candles,
        })
        return result
