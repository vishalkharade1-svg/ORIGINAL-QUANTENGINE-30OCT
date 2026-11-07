"""Phase 25 controlled paper-session harness tests (offline, zero network).

Fake history + mutable fake clock drive the REAL engine assembly
(ExplicitSymbolUniverseManager -> MultiSymbolSubscriptionManager ->
RealTimeEngine -> PaperRuntime -> BrokerEngine dry-run) exactly as the
live Mode-A session does, with every delivery produced by the
instrumented REST transport. All artifacts are written to tmp_path.

No exchange connection is used anywhere in this file: "live"-mode
sessions here are the LIVE CODE PATH exercised against a fake REST
history, clearly labelled as such in the report (market_data_source is
whatever the runner was configured with; the endpoint field is only
truthful when the real DeltaHistory client is used).
"""

from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path

import pytest

from core.history.candle import Candle
from data.paper_session.paper_session import (
    FILL_CLASS,
    SESSION_MODE_LIVE,
    SESSION_MODE_REPLAY,
    InstrumentedRestTransport,
    PaperSessionRunner,
    refuse_live_execution,
    run_replay_session,
)

BASE_TS = 1_700_000_400  # minute-aligned (gap-repair semantics)
MINUTE = 60


class FakeClock:
    def __init__(self, now):
        self.now = float(now)
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            return self.now

    def advance(self, seconds):
        with self._lock:
            self.now += seconds


def _ohlc(seed, stamp):
    """Deterministic pseudo-walk OHLCV for one bucket."""
    value = (seed * 1103515245 + stamp * 12345 + 6789) % 100000
    drift = (value % 100) - 50
    o = 60000.0 + drift
    c = o + (value % 17) - 8
    h = max(o, c) + (value % 5)
    low = min(o, c) - (value % 5)
    volume = 10.0 + (value % 40)
    return o, h, low, c, volume


class DynamicHistory:
    """Fake REST history: returns recent closed 1m buckets for the
    current fake clock (the real endpoint's behaviour). Optionally
    omits one bucket to exercise gap handling."""

    def __init__(self, clock, *, seed=7, window=10, skip_at=None):
        self.clock = clock
        self.seed = seed
        self.window = window
        self.skip_at = skip_at
        self.calls = 0
        self.lock = threading.Lock()

    def candles(self, symbol, resolution="1m", start=None, end=None,
                days=1):
        with self.lock:
            self.calls += 1
        now = int(self.clock())
        last_closed = (now // MINUTE) * MINUTE - MINUTE
        first = last_closed - (self.window - 1) * MINUTE
        rows = []
        for stamp in range(first, last_closed + 1, MINUTE):
            if self.skip_at is not None and stamp == self.skip_at:
                continue
            o, h, low, c, v = _ohlc(self.seed, stamp)
            rows.append(Candle(timestamp=stamp, open=o, high=h,
                               low=low, close=c, volume=v, symbol=""))
        return rows


class TinyHistory:
    """Minimal history whose candles() accepts (symbol, resolution,
    days) only -- proves the counting proxy's tolerant call shape."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def candles(self, symbol, resolution="1m", days=1):
        self.calls += 1
        return list(self.rows)


def _set_fast_poll(monkeypatch):
    from config import settings as settings_module

    monkeypatch.setattr(settings_module.settings,
                        "CONTROL_API_POLL_SECONDS", 0.05)


def _advance_clock_forever(clock, step=MINUTE, period=0.25):
    stop = threading.Event()

    def loop():
        while not stop.wait(period):
            clock.advance(step)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return stop


class TestPaperSessionModeA:
    def test_live_path_delivers_closes_and_reconciles(self, tmp_path,
                                                      monkeypatch):
        _set_fast_poll(monkeypatch)
        clock = FakeClock(BASE_TS + 30 * MINUTE)
        history = DynamicHistory(clock, seed=11)
        runner = PaperSessionRunner(
            ["BTCUSDT"],
            timeframe="1m",
            run_seconds=4.0,
            heartbeat_seconds=1.0,
            poll_interval_seconds=15.0,
            lookback_days=1,
            output_dir=str(tmp_path),
            session_id="P25-TEST-LIVE",
            history=history,
            clock=clock,
        )
        advance_stop = _advance_clock_forever(clock)
        try:
            report = runner.run()
        finally:
            advance_stop.set()
        assert report["session_mode"] == SESSION_MODE_LIVE
        assert report["evidence_class"] == "EXCHANGE_SOURCED_PAPER_SIMULATION"
        assert report["fills_are"] == FILL_CLASS
        assert report["preliminary"] is True
        quality = report["market_data"]["delivered_quality"]["BTCUSDT"]
        assert quality["delivered"] >= 5
        assert quality["ascending"] is True
        assert quality["duplicate_buckets"] == 0
        assert quality["internal_missing_buckets"] == 0
        assert report["market_data"]["live_delivered"]["BTCUSDT"] >= 1
        assert report["market_data"]["warmup_delivered"]["BTCUSDT"] >= 1
        assert report["engine"]["routed"] >= 1
        assert report["engine"]["route_errors"] == 0
        assert report["reconciliation"]["consistent"] is True
        session_dir = tmp_path / "P25-TEST-LIVE"
        assert (session_dir / "session_report.json").exists()
        assert (session_dir / "delivered_candles.jsonl").exists()
        assert (session_dir / "session_summary.md").exists()
        lines = (session_dir / "delivered_candles.jsonl").read_text(
            encoding="utf-8").splitlines()
        header = json.loads(lines[0])
        assert header["provenance"]["session_mode"] == SESSION_MODE_LIVE
        assert header["provenance"]["fills_are"] == FILL_CLASS
        assert header["provenance"]["market_data_source"] == \
            report["market_data_source"]
        # Every captured row is a closed-bucket record with OHLCV.
        rows = [json.loads(line) for line in lines[1:]]
        assert rows
        for row in rows:
            assert row["symbol"] == "BTCUSDT"
            assert row["bucket_open_ts"] % MINUTE == 0
            assert row["volume"] > 0

    def test_gap_is_never_bridged_and_is_counted(self, tmp_path,
                                                 monkeypatch):
        _set_fast_poll(monkeypatch)
        clock = FakeClock(BASE_TS + 30 * MINUTE)
        # The bucket right after the warm-up window start is missing:
        # once later buckets deliver, that bucket can never be
        # re-delivered (watermark + router ordering) -> permanent,
        # counted gap.
        skip_at = (BASE_TS // MINUTE) * MINUTE + 27 * MINUTE
        history = DynamicHistory(clock, seed=5, skip_at=skip_at)
        runner = PaperSessionRunner(
            ["BTCUSDT"],
            timeframe="1m",
            run_seconds=3.5,
            heartbeat_seconds=1.0,
            output_dir=str(tmp_path),
            session_id="P25-TEST-GAP",
            history=history,
            clock=clock,
        )
        advance_stop = _advance_clock_forever(clock)
        try:
            report = runner.run()
        finally:
            advance_stop.set()
        quality = report["market_data"]["delivered_quality"]["BTCUSDT"]
        stamps = [row["bucket_open_ts"]
                  for row in runner.transport.delivered_candles()["BTCUSDT"]]
        assert skip_at not in stamps
        assert quality["internal_missing_buckets"] >= 1
        # The engine never saw a bridged candle: route errors stay 0.
        assert report["engine"]["route_errors"] == 0

    def test_endpoint_failure_is_clear_not_silent(self, tmp_path,
                                                  monkeypatch):
        _set_fast_poll(monkeypatch)

        class DownHistory:
            def candles(self, *a, **k):
                raise ConnectionError("unreachable")

        clock = FakeClock(BASE_TS + 30 * MINUTE)
        runner = PaperSessionRunner(
            ["BTCUSDT"],
            timeframe="1m",
            run_seconds=2.5,
            heartbeat_seconds=1.0,
            output_dir=str(tmp_path),
            session_id="P25-TEST-DOWN",
            history=DownHistory(),
            clock=clock,
        )
        report = runner.run()
        # Clear failure accounting: no silent fixture substitution.
        assert report["market_data"]["rest_history"]["errors"] >= 1
        assert report["market_data"]["rest_history"]["rows_seen"] == 0
        stream = report["market_data"]["transport_stats"].get(
            "BTCUSDT", {})
        assert stream.get("delivered", 0) == 0
        assert report["engine"]["routed"] == 0
        # The ledger still reconciles at zero trades (no invented state).
        assert report["reconciliation"]["consistent"] is True
        summary = (tmp_path / "P25-TEST-DOWN" / "session_summary.md"
                   ).read_text(encoding="utf-8")
        assert "errors" in summary

    def test_repeat_run_starts_fresh_in_memory(self, tmp_path,
                                               monkeypatch):
        _set_fast_poll(monkeypatch)
        clock = FakeClock(BASE_TS + 30 * MINUTE)
        history = DynamicHistory(clock, seed=3)
        advance_stop = _advance_clock_forever(clock)
        try:
            first = PaperSessionRunner(
                ["BTCUSDT"], timeframe="1m", run_seconds=2.0,
                heartbeat_seconds=1.0, output_dir=str(tmp_path),
                session_id="P25-TEST-R1", history=history, clock=clock,
            ).run()
            second = PaperSessionRunner(
                ["BTCUSDT"], timeframe="1m", run_seconds=2.0,
                heartbeat_seconds=1.0, output_dir=str(tmp_path),
                session_id="P25-TEST-R2", history=history, clock=clock,
            ).run()
        finally:
            advance_stop.set()
        first_bars = sum(r["processed_bars"]
                         for r in first["runtimes"])
        second_bars = sum(r["processed_bars"]
                          for r in second["runtimes"])
        # No cross-session persistence: the second session starts its
        # own warm-up (documents the in-memory paper-state limitation).
        assert first_bars >= 1
        assert second_bars >= 1
        assert second["session_id"] == "P25-TEST-R2"
        assert first["session_id"] == "P25-TEST-R1"

    def test_refuses_live_arming(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LIVE_MODE", "1")
        with pytest.raises(SystemExit):
            PaperSessionRunner(
                ["BTCUSDT"], output_dir=str(tmp_path),
                history=DynamicHistory(FakeClock(BASE_TS)),
            )
        monkeypatch.setenv("LIVE_MODE", "")
        monkeypatch.setenv("EXECUTION_MODE", "LIVE")
        with pytest.raises(SystemExit):
            PaperSessionRunner(
                ["BTCUSDT"], output_dir=str(tmp_path),
                history=DynamicHistory(FakeClock(BASE_TS)),
            )

    def test_invalid_inputs_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            PaperSessionRunner([], output_dir=str(tmp_path))
        with pytest.raises(ValueError):
            PaperSessionRunner(["BTCUSDT"], timeframe="7m",
                               output_dir=str(tmp_path))

    def test_counting_history_tolerant_call_shape(self, tmp_path):
        proxy_rows = [Candle(timestamp=BASE_TS, open=1, high=2, low=0.5,
                             close=1.5, volume=3, symbol="")]
        inner = TinyHistory(proxy_rows)
        transport = InstrumentedRestTransport(
            timeframe="1m", history=inner,
            clock=FakeClock(BASE_TS + 2 * MINUTE),
            poll_interval_seconds=15.0, lookback_days=1,
        )
        seen = []
        transport.subscribe("BTCUSDT", seen.append, lambda: None)
        try:
            deadline = time.time() + 10.0
            while time.time() < deadline and len(seen) < 1:
                time.sleep(0.05)
            assert [c.timestamp for c in seen] == [BASE_TS]
            stats = transport.stats("BTCUSDT")["BTCUSDT"]
            assert stats["delivered"] == 1
        finally:
            transport.close()

    def test_cost_profile_is_recorded_not_assumed(self, monkeypatch):
        from config import risk_settings as rs
        from core.risk import costs as costs_module
        from data.paper_session.paper_session import (
            _cost_profile_snapshot,
        )

        monkeypatch.setattr(rs, "PAPER_COMMISSION_PER_TRADE", 0.05)
        monkeypatch.setattr(rs, "PAPER_COMMISSION_RATE", 0.0005)
        monkeypatch.setattr(rs, "PAPER_SLIPPAGE_BPS", 5.0)
        monkeypatch.setattr(rs, "PAPER_COST_PROFILE_NAME",
                            "p25-conservative-assumption")
        monkeypatch.setattr(rs, "PAPER_COST_VENUE_REALISTIC", False)
        snapshot = _cost_profile_snapshot()
        assert snapshot["profile_name"] == "p25-conservative-assumption"
        assert snapshot["classification"] == \
            costs_module.CONFIGURED_SIMULATION
        assert snapshot["venue_realistic"] is False
        assert snapshot["rate"] == 0.0005
        assert snapshot["slippage_bps"] == 5.0

    def test_shutdown_midrun_writes_artifacts(self, tmp_path,
                                              monkeypatch):
        _set_fast_poll(monkeypatch)
        clock = FakeClock(BASE_TS + 30 * MINUTE)
        history = DynamicHistory(clock, seed=17)
        runner = PaperSessionRunner(
            ["BTCUSDT"],
            timeframe="1m",
            run_seconds=2.0,
            heartbeat_seconds=1.0,
            output_dir=str(tmp_path),
            session_id="P25-TEST-SHUTDOWN",
            history=history,
            clock=clock,
        )
        receipt = runner.start()
        assert receipt["session_id"] == "P25-TEST-SHUTDOWN"
        runner.request_stop("test_stop")
        report = runner.run()  # idempotent stop; finalizes artifacts
        assert report["provenance"]["stop_reason"] in (
            "test_stop", "run_seconds_elapsed", "completed")
        assert (tmp_path / "P25-TEST-SHUTDOWN" /
                "session_report.json").exists()


class TestPaperSessionModeB:
    def test_synthetic_replay_is_labelled_not_live(self, tmp_path):
        report = run_replay_session(
            synthetic_seed=99, synthetic_candles=90,
            output_dir=str(tmp_path), session_id="P25-TEST-REPLAY-SYN",
        )
        assert report["session_mode"] == SESSION_MODE_REPLAY
        assert report["evidence_class"] == "SYNTHETIC_FIXTURE"
        assert report["market_data_endpoint"] is None
        assert report["fills_are"] == FILL_CLASS
        p24 = report["phase24_report"]
        assert p24["counts"]["frames_input"] == 90
        assert p24["counts"]["frames_ingested"] == 90
        summary = (Path(report["artifact_paths"]["session_summary"])
                   .read_text(encoding="utf-8"))
        assert "NOT a live market session" in summary

    def test_capture_replay_carries_evidence_class(self, tmp_path):
        from data.realtime.verified_replay import (
            synthetic_candle_frames,
        )

        frames = synthetic_candle_frames(
            "BTCUSDT", candles=60, seed=7, start_ts_seconds=BASE_TS)
        bundle = {
            "schema": "quantengine.delta-public-capture.v1",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "synthetic": True,
            "endpoint": "synthetic://phase25-test",
            "symbol": "BTCUSDT",
            "note": "phase25 test bundle",
            "frames": [
                {
                    "receipt_ordinal": r.ordinal,
                    "receipt_unix_ns": r.receipt_ns,
                    "synthetic": True,
                    "frame": r.frame,
                }
                for r in frames
            ],
        }
        capture_path = tmp_path / "bundle.json"
        capture_path.write_text(json.dumps(bundle), encoding="utf-8")
        report = run_replay_session(
            capture_path=str(capture_path),
            output_dir=str(tmp_path),
            session_id="P25-TEST-REPLAY-CAP",
        )
        assert report["evidence_class"] == "SYNTHETIC_FIXTURE"
        assert report["phase24_report"]["counts"][
            "frames_ingested"] == 60

    def test_replay_fault_tokens_are_applied(self, tmp_path):
        from scripts.run_paper_session import _parse_faults

        plans = _parse_faults(["duplicate@50", "out_of_order@60:3",
                               "malformed@70:drop_volume",
                               "gap@80:2", "disconnect@90:2"])
        kinds = [type(p).__name__ for p in plans]
        assert kinds == ["DuplicateFault", "OutOfOrderFault",
                         "MalformedFault", "GapFault", "DisconnectFault"]
        report = run_replay_session(
            synthetic_seed=99, synthetic_candles=120,
            faults=plans, output_dir=str(tmp_path),
            session_id="P25-TEST-REPLAY-FAULTS",
        )
        applied = report["phase24_report"]["faults_applied"]
        assert len(applied) == 5
        # Only the malformed + disconnect faults inject synthetic
        # frames; duplicate/out-of-order re-ingest captured frames and
        # gap faults skip frames (all counted, none fabricated).
        assert report["phase24_report"]["counts"][
            "synthetic_frames_injected"] >= 1


class TestSessionSafetyAndContracts:
    def test_refuse_live_execution_messages(self, monkeypatch):
        monkeypatch.setenv("LIVE_MODE", "true")
        with pytest.raises(SystemExit, match="REFUSED"):
            refuse_live_execution()
        monkeypatch.setenv("LIVE_MODE", "")
        monkeypatch.setenv("EXECUTION_MODE", "live")
        with pytest.raises(SystemExit, match="REFUSED"):
            refuse_live_execution()
        monkeypatch.setenv("EXECUTION_MODE", "WEIRD")
        with pytest.raises(SystemExit, match="REFUSED"):
            refuse_live_execution()
        monkeypatch.setenv("EXECUTION_MODE", "PAPER")
        refuse_live_execution()  # accepted

    def test_delivery_quality_audit_math(self):
        from data.paper_session.paper_session import _delivery_quality

        rows = [
            {"bucket_open_ts": 120, "symbol": "S"},
            {"bucket_open_ts": 180, "symbol": "S"},
            {"bucket_open_ts": 300, "symbol": "S"},  # 240 missing
        ]
        out = _delivery_quality({"S": rows}, 60)
        entry = out["S"]
        assert entry["delivered"] == 3
        assert entry["duplicate_buckets"] == 0
        assert entry["internal_missing_buckets"] == 1
        assert entry["ascending"] is True
        assert entry["window_aligned"] is True
        aligned_break = [
            {"bucket_open_ts": 101, "symbol": "X"},
            {"bucket_open_ts": 161, "symbol": "X"},
        ]
        out2 = _delivery_quality({"X": aligned_break}, 60)
        assert out2["X"]["window_aligned"] is False

    def test_no_order_write_path_in_session_stack(self):
        import io

        from data.paper_session import paper_session as module

        source = io.open(module.__file__, encoding="utf-8").read()
        for banned in ("place_order", "submit_order", "create_order",
                       "cancel_order", "requests.post", "session.post"):
            assert banned not in source, banned


if __name__ == "__main__":
    unittest.main()
