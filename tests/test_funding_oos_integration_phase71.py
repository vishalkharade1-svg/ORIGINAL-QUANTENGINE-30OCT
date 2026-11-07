import hashlib
import json

import pytest

from core.execution.economics import FundingEvent, FundingSchedule
from core.backtesting.trade_simulator import TradeSimulator
from core.research.oos_validation.execution import run_frozen_oos, load_verified_funding_schedule
from research.economics.funding_evidence import _canonical_payload, build_artifact, write_artifact


def test_funding_schedule_coverage_is_fail_closed():
    schedule = FundingSchedule([
        FundingEvent(200, 0.001, "test"),
        FundingEvent(300, 0.001, "test"),
    ])
    assert schedule.covers(200, 300)
    assert not schedule.covers(199, 300)
    assert not schedule.covers(200, 301)


def test_funding_schedule_is_wired_to_backtester():
    from backtesting.backtester import Backtester

    class Pipeline:
        def __init__(self):
            self.context = type("Context", (), {"reset_cycle": lambda self: None})()
        def reset(self):
            pass

    class Bus:
        pass

    schedule = FundingSchedule([FundingEvent(100, 0.001, "test")])
    simulator = TradeSimulator()
    bt = Backtester(Pipeline(), Bus(), simulator, funding_schedule=schedule)
    assert bt.funding_schedule is schedule
    assert simulator.funding_schedule is schedule


def test_frozen_oos_rejects_incomplete_funding_coverage_before_execution():
    rows = [
        {"time": 100, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"time": 200, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
    ]
    schedule = FundingSchedule([FundingEvent(150, 0.001, "test")])
    with pytest.raises(ValueError, match="does not cover"):
        run_frozen_oos(rows, funding_schedule=schedule)


def test_trade_simulator_funding_is_holding_interval_only():
    schedule = FundingSchedule([
        FundingEvent(100, 0.001, "test"),
        FundingEvent(200, 0.002, "test"),
        FundingEvent(300, 0.004, "test"),
    ])
    sim = TradeSimulator(funding_schedule=schedule)
    class Setup:
        direction = "BULLISH"
        entry = 100.0
        stop_loss = 90.0
        take_profit = 120.0
        quantity = 1.0
        exit_mode = "FIXED_TARGET"
        trailing_enabled = False
        trailing_activation_r = 0.0
        trailing_distance_r = 0.0
        setup_id = "phase71"
        order_id = "phase71-order"
        trade_id = "phase71-trade"
        risk_amount = 10.0

    sim.open_trade(Setup(), timestamp=150)
    sim.request_exit(250, 100.0, reason="TEST")
    trade = sim.registry.all()[0]
    assert trade.funding == pytest.approx(0.2)
    assert trade.funding_events == 1


def test_verified_funding_artifact_loader_binds_market_bytes_and_window(tmp_path):
    market = tmp_path / "market.json"
    market.write_text("exact-market-bytes\n", encoding="utf-8")
    request = {"symbol": "FUNDING:BTCUSDT", "resolution": "1h", "start": 100, "end": 300}
    events = [{"time": 200, "rate": 0.001}]
    evidence = {"request": request, "events": events,
                "sha256": hashlib.sha256(_canonical_payload(request, events)).hexdigest()}
    artifact = build_artifact(evidence, market_data_path=market, provenance_status="REAL", captured_at="2026-10-07T00:00:00Z")
    artifact_path = tmp_path / "funding.json"
    write_artifact(artifact, artifact_path)
    schedule = load_verified_funding_schedule(artifact_path, market, [
        {"time": 150}, {"time": 250}
    ])
    assert schedule.covers(150, 250)
    market.write_text("mutated-market-bytes\n", encoding="utf-8")
    with pytest.raises(ValueError, match="market-data evidence hash mismatch"):
        load_verified_funding_schedule(artifact_path, market, [{"time": 150}, {"time": 250}])
