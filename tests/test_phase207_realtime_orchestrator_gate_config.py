from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.runtime import realtime_engine as realtime_module
from core.runtime.gated_realtime_engine import GatedRealTimeEngine

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def test_gated_orchestrator_rejects_invalid_age_tolerance():
    for value in (float("nan"), float("inf"), -1, "bad"):
        with pytest.raises(ValueError):
            GatedRealTimeEngine(universe_manager=object(), market_data_max_age_seconds=value)


def test_gated_orchestrator_rejects_non_callable_clock_provider():
    with pytest.raises(ValueError):
        GatedRealTimeEngine(
            universe_manager=object(), market_data_max_age_seconds=10,
            market_data_now_provider=NOW,
        )


def test_gated_orchestrator_passes_gate_config_to_each_new_paper_runtime(monkeypatch):
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
    engine = GatedRealTimeEngine.__new__(GatedRealTimeEngine)
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
    assert captured[0]["instrument"] is instrument
    assert key in engine.runtimes


def test_canonical_orchestrator_supports_optional_gate_and_legacy_default():
    from core.runtime.realtime_engine import RealTimeEngine
    assert GatedRealTimeEngine is RealTimeEngine
    legacy = RealTimeEngine(universe_manager=object())
    assert legacy.market_data_max_age_seconds is None
    gated = RealTimeEngine(
        universe_manager=object(), market_data_max_age_seconds=10,
        market_data_now_provider=lambda: NOW,
    )
    assert gated.market_data_max_age_seconds == 10
    assert gated.market_data_now_provider() == NOW
