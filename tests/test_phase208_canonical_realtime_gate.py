from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.runtime import realtime_engine as realtime_module
from core.runtime.realtime_engine import RealTimeEngine

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def test_canonical_engine_rejects_bad_threshold_and_clock():
    for value in (float("nan"), float("inf"), -1, "bad"):
        with pytest.raises(ValueError):
            RealTimeEngine(universe_manager=object(), market_data_max_age_seconds=value)
    with pytest.raises(ValueError):
        RealTimeEngine(
            universe_manager=object(), market_data_max_age_seconds=5,
            market_data_now_provider=NOW,
        )


def test_canonical_engine_passes_gate_to_every_new_runtime(monkeypatch):
    captured = []

    class RuntimeSpy:
        def __init__(self, **kwargs):
            captured.append(kwargs)
        def retire(self):
            pass

    instrument = SimpleNamespace(symbol="BTCUSDT", exchange="DEMO", instrument_id="BTC-1")
    pipeline = SimpleNamespace(instrument=instrument)
    key = ("DEMO", "BTC-1")

    class RegistrySpy:
        def reconcile(self, instruments):
            assert instruments == [instrument]
            return {"added": [key], "retained": [], "retired": []}
        def get(self, requested_key):
            assert requested_key == key
            return pipeline

    class SubscriptionSpy:
        def sync(self, instruments):
            assert instruments == [instrument]

    monkeypatch.setattr(realtime_module, "PaperRuntime", RuntimeSpy)
    engine = RealTimeEngine.__new__(RealTimeEngine)
    engine.market_data_max_age_seconds = 12.5
    engine.market_data_now_provider = lambda: NOW
    engine.registry = RegistrySpy()
    engine.runtimes = {}
    engine.starting_balance = 1234
    engine.journal = None
    engine.subscriptions = SubscriptionSpy()
    engine._portfolio_gate = lambda *a, **k: True
    engine._portfolio_release = lambda *a, **k: None

    class Universe:
        def eligible_instruments(self):
            return [instrument]

    engine._reconcile(Universe())
    assert len(captured) == 1
    assert captured[0]["market_data_max_age_seconds"] == 12.5
    assert captured[0]["market_data_now_provider"]() == NOW
    assert engine.runtimes[key] is not None


def test_default_engine_keeps_gate_disabled_for_compatibility():
    engine = RealTimeEngine(universe_manager=object())
    assert engine.market_data_max_age_seconds is None
    assert engine.market_data_now_provider is None
