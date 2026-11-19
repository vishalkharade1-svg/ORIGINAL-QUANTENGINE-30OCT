from datetime import datetime, timezone
from types import SimpleNamespace

from core.history.candle import Candle
from core.runtime.paper_runtime import PaperRuntime

NOW = datetime(2026, 10, 25, 4, 30, tzinfo=timezone.utc)


class EngineSpy:
    def __init__(self):
        self.calls = []

    def run_candle(self, candle):
        self.calls.append(candle)


class ContextSpy:
    pass


def runtime_for_test(symbol="BTCUSD", max_age=5):
    runtime = PaperRuntime.__new__(PaperRuntime)
    runtime.instrument = SimpleNamespace(symbol=symbol, exchange="fixture", instrument_id="1")
    runtime.pipeline = SimpleNamespace(context=ContextSpy())
    runtime.journal = None
    runtime.retired = False
    runtime.market_data_max_age_seconds = max_age
    runtime.market_data_now_provider = lambda: NOW
    runtime.market_data_gate_decisions = []
    runtime.rejected_market_data_candles = 0
    runtime.engine = EngineSpy()
    return runtime


def candle(symbol="BTCUSD", timestamp=None):
    timestamp = int(NOW.timestamp()) if timestamp is None else timestamp
    return Candle(timestamp=timestamp, open=100, high=102, low=99, close=101,
                  volume=1, closed=True, symbol=symbol)


def test_valid_candle_passes_gate_and_reaches_paper_engine():
    runtime = runtime_for_test()
    item = candle()
    assert runtime.process_closed_candle(item) is True
    assert runtime.engine.calls == [item]
    assert runtime.rejected_market_data_candles == 0
    assert runtime.market_data_gate_decisions[-1].accepted


def test_stale_candle_is_rejected_before_strategy_or_engine_runs():
    runtime = runtime_for_test(max_age=2)
    item = candle(timestamp=int(NOW.timestamp()) - 20)
    assert runtime.process_closed_candle(item) is False
    assert runtime.engine.calls == []
    assert runtime.rejected_market_data_candles == 1
    assert "MARKET_DATA_STALE" in runtime.market_data_gate_decisions[-1].reason_codes


def test_missing_or_mismatched_symbol_fails_closed():
    runtime = runtime_for_test(symbol="BTCUSD")
    item = candle(symbol="ETHUSD")
    assert runtime.process_closed_candle(item) is False
    assert runtime.engine.calls == []
    assert "SYMBOL_MISMATCH" in runtime.market_data_gate_decisions[-1].reason_codes


def test_gate_disabled_preserves_legacy_runtime_path():
    runtime = runtime_for_test(max_age=None)
    item = candle(timestamp=1)
    assert runtime.process_closed_candle(item) is None
    assert runtime.engine.calls == [item]
    assert runtime.market_data_gate_decisions == []


def test_forming_candle_is_rejected_before_strategy_runs():
    runtime = runtime_for_test()
    item = candle()
    item.closed = False
    assert runtime.process_closed_candle(item) is False
    assert runtime.engine.calls == []
    assert "CANDLE_NOT_CLOSED" in runtime.market_data_gate_decisions[-1].reason_codes


def test_inconsistent_ohlc_is_rejected_before_strategy_runs():
    runtime = runtime_for_test()
    item = candle()
    item.high = 98  # lower than close; invalid candle envelope
    assert runtime.process_closed_candle(item) is False
    assert runtime.engine.calls == []
    assert "CANDLE_NORMALIZATION_INVALID" in runtime.market_data_gate_decisions[-1].reason_codes
