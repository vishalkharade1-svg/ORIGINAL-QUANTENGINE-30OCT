from datetime import datetime, timezone
from types import SimpleNamespace

from core.history.candle import Candle
from core.runtime.gated_paper_entrypoints import (
    GatedPaperTradingEngine,
    GatedVerifiedPaperRuntime,
)

NOW = datetime(2026, 10, 25, 5, 0, tzinfo=timezone.utc)


def candle(symbol="BTCUSDT", timestamp=None, *, closed=True, high=102):
    return Candle(
        timestamp=int(NOW.timestamp()) if timestamp is None else timestamp,
        open=100, high=high, low=99, close=101, volume=1,
        closed=closed, symbol=symbol,
    )


class PipelineSpy:
    def __init__(self):
        self.context = SimpleNamespace(market=SimpleNamespace(symbol="BTCUSDT"))
        self.calls = []

    def on_candle(self, event):
        self.calls.append(event)


def test_gated_paper_trading_engine_rejects_stale_before_pipeline():
    engine = GatedPaperTradingEngine.__new__(GatedPaperTradingEngine)
    engine.pipeline = PipelineSpy()
    engine.market_data_max_age_seconds = 5
    engine.market_data_expected_symbol = "BTCUSDT"
    engine.market_data_now_provider = lambda: NOW
    engine.market_data_gate_decisions = []
    engine.rejected_market_data_candles = 0

    assert engine.run_candle(candle(timestamp=int(NOW.timestamp()) - 30)) is False
    assert engine.pipeline.calls == []
    assert engine.rejected_market_data_candles == 1
    assert "MARKET_DATA_STALE" in engine.market_data_gate_decisions[-1].reason_codes


def test_gated_paper_trading_engine_rejects_wrong_symbol_before_pipeline():
    engine = GatedPaperTradingEngine.__new__(GatedPaperTradingEngine)
    engine.pipeline = PipelineSpy()
    engine.market_data_max_age_seconds = 5
    engine.market_data_expected_symbol = "BTCUSDT"
    engine.market_data_now_provider = lambda: NOW
    engine.market_data_gate_decisions = []
    engine.rejected_market_data_candles = 0

    assert engine.run_candle(candle(symbol="ETHUSDT")) is False
    assert engine.pipeline.calls == []
    assert "SYMBOL_MISMATCH" in engine.market_data_gate_decisions[-1].reason_codes


def test_gated_verified_runtime_blocks_stale_before_paper_sink():
    runtime = GatedVerifiedPaperRuntime.__new__(GatedVerifiedPaperRuntime)
    runtime.symbols = ["BTCUSDT"]
    delivered = []
    runtime.paper_sink = lambda item: delivered.append(item)
    runtime.market_data_max_age_seconds = 5
    runtime.market_data_now_provider = lambda: NOW
    runtime.market_data_gate_decisions = []
    runtime.rejected_market_data_candles = 0
    runtime._on_verified_candle(candle(timestamp=int(NOW.timestamp()) - 30))

    assert delivered == []
    assert runtime.rejected_market_data_candles == 1
    assert "MARKET_DATA_STALE" in runtime.market_data_gate_decisions[-1].reason_codes


def test_gated_verified_runtime_rejects_unsubscribed_symbol():
    runtime = GatedVerifiedPaperRuntime.__new__(GatedVerifiedPaperRuntime)
    runtime.symbols = ["BTCUSDT"]
    delivered = []
    runtime.paper_sink = lambda item: delivered.append(item)
    runtime.market_data_max_age_seconds = 5
    runtime.market_data_now_provider = lambda: NOW
    runtime.market_data_gate_decisions = []
    runtime.rejected_market_data_candles = 0
    runtime._on_verified_candle(candle(symbol="ETHUSDT"))

    assert delivered == []
    assert runtime.rejected_market_data_candles == 1
    assert "SYMBOL_MISMATCH" in runtime.market_data_gate_decisions[-1].reason_codes


def test_gated_verified_runtime_accepts_fresh_subscribed_candle():
    runtime = GatedVerifiedPaperRuntime.__new__(GatedVerifiedPaperRuntime)
    runtime.symbols = ["BTCUSDT"]
    delivered = []
    runtime.paper_sink = lambda item: delivered.append(item)
    runtime.market_data_max_age_seconds = 5
    runtime.market_data_now_provider = lambda: NOW
    runtime.market_data_gate_decisions = []
    runtime.rejected_market_data_candles = 0
    item = candle()
    runtime._on_verified_candle(item)

    assert delivered == [item]
    assert runtime.rejected_market_data_candles == 0
    assert runtime.market_data_gate_decisions[-1].accepted


def test_gated_paper_engine_clock_failure_fails_closed():
    engine = GatedPaperTradingEngine.__new__(GatedPaperTradingEngine)
    engine.pipeline = PipelineSpy()
    engine.market_data_max_age_seconds = 5
    engine.market_data_expected_symbol = "BTCUSDT"
    def broken_clock():
        raise RuntimeError("clock unavailable")
    engine.market_data_now_provider = broken_clock
    engine.market_data_gate_decisions = []
    engine.rejected_market_data_candles = 0

    assert engine.run_candle(candle()) is False
    assert engine.pipeline.calls == []
    assert engine.market_data_gate_decisions[-1].reason_codes == ("MARKET_DATA_GATE_ERROR",)


def test_gated_entrypoint_constructor_rejects_nonfinite_age_tolerance():
    import pytest
    with pytest.raises(ValueError):
        GatedPaperTradingEngine(
            pipeline=PipelineSpy(), event_bus=None,
            market_data_max_age_seconds=float("nan"),
        )
