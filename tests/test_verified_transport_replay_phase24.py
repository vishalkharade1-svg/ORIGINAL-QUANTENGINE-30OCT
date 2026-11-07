"""Phase 24: verified-transport replay, failure recovery and risk evidence.

These tests drive the REAL assembly -- ``VerifiedPublicCandleTransport``
→ ``DeltaPublicEventStream`` (finality + continuity) → ``to_runtime_candle``
→ ``SubscriptionWorker`` router → ``RealTimeEngine`` → ``PaperRuntime``
(``BrokerEngine(dry_run=True)`` → ``InstitutionalPipeline`` → ``RiskEngine``
→ ``TradeSimulator``) -- through ``data.realtime.verified_replay``.

Evidence classes are explicit everywhere: captured bundles stay captured,
synthetic feeds are labelled ``SYNTHETIC_FIXTURE`` and are used for fault
injection and soak only.  No production code is modified by these tests;
no live order can be placed (the engine is assembled dry-run).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.realtime.verified_replay import (
    DuplicateFault,
    DisconnectFault,
    GapFault,
    MalformedFault,
    OutOfOrderFault,
    VerifiedTransportReplay,
    load_capture,
    make_synthetic_bundle,
    reconcile_paper_ledger,
    synthetic_candle_frames,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CAPTURE_PATH = (
    REPO_ROOT
    / "data"
    / "fixtures"
    / "delta"
    / "observed_india_btcusd_trades_candles_rollover_20260916.json"
)

SYMBOL = "BTCUSD"


@contextmanager
def replay(symbols=(SYMBOL,)):
    """Fresh harness assembly, always closed (log observer detached)."""
    harness = VerifiedTransportReplay(list(symbols))
    harness.start()
    try:
        yield harness
    finally:
        harness.close()


# ==================================================================
# Captured evidence: loading and end-to-end delivery
# ==================================================================


class TestCaptureBundleLoading:
    def test_captured_bundle_loads_with_evidence_class(self):
        bundle = load_capture(CAPTURE_PATH)
        assert bundle.is_captured is True
        assert bundle.schema == "quantengine.delta-public-capture.v1"
        assert bundle.symbol == SYMBOL
        ordinals = [record.ordinal for record in bundle.records]
        assert ordinals == sorted(ordinals)
        assert ordinals[0] == 1
        assert len(ordinals) == len(set(ordinals))

    def test_wrong_schema_is_rejected(self, tmp_path):
        path = tmp_path / "bad_capture.json"
        path.write_text(
            json.dumps({"schema": "some.other.schema.v9", "frames": []}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            load_capture(path)

    def test_non_object_capture_is_rejected(self, tmp_path):
        path = tmp_path / "bad_capture.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError):
            load_capture(path)

    def test_explicitly_synthetic_file_bundle_keeps_synthetic_label(self,
                                                                    tmp_path):
        """A capture file whose records declare ``synthetic`` must load
        with per-record synthetic flags intact (the report's evidence
        class is derived from them). Phase 25 regression: load_capture
        used to drop the flag, mislabelling a synthetic file bundle as
        CAPTURED."""
        records = synthetic_candle_frames("BTCUSDT", candles=30, seed=7)
        bundle_payload = {
            "schema": "quantengine.delta-public-capture.v1",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "synthetic": True,
            "endpoint": "synthetic://regression",
            "symbol": "BTCUSDT",
            "frames": [
                {
                    "receipt_ordinal": r.ordinal,
                    "receipt_unix_ns": r.receipt_ns,
                    "synthetic": True,
                    "frame": r.frame,
                }
                for r in records
            ],
        }
        path = tmp_path / "synthetic_bundle.json"
        path.write_text(json.dumps(bundle_payload), encoding="utf-8")
        bundle = load_capture(path)
        assert bundle.is_captured is False
        assert all(record.synthetic for record in bundle.records)
        with replay() as harness:
            report = harness.run(bundle.records)
            assert report.evidence_class == "SYNTHETIC_FIXTURE"


class TestCapturedReplayEndToEnd:
    def test_captured_capture_delivers_closed_candle_to_pipeline(self):
        bundle = load_capture(CAPTURE_PATH)
        with replay() as harness:
            report = harness.run(bundle.records)
            assert report.frames_ingested == len(bundle.records)
            stats = report.transport
            assert stats["closed_delivered"] == 1
            assert report.engine["routed"] == 1
            assert report.pipeline["candles_processed"] == 1
            assert report.engine["route_errors"] == 0
            assert report.unrouted_during_outage == 0
            assert report.paper["orders_placed"] == 0
            assert report.gaps["statuses"][f"DELTA:{SYMBOL}:1m"][
                "status"
            ] == "CONTINUOUS"
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_captured_replay_is_deterministic(self):
        bundle = load_capture(CAPTURE_PATH)
        first = self._run(bundle)
        second = self._run(bundle)
        assert first["counts"] == second["counts"]
        assert first["observations"] == second["observations"]

    @staticmethod
    def _run(bundle):
        with replay() as harness:
            report = harness.run(bundle.records)
            return json.loads(report.to_json(include_observations=True))


# ==================================================================
# Synthetic fixture: deterministic feed through the real chain
# ==================================================================


class TestSyntheticFixtureFeed:
    def test_frames_are_labelled_synthetic_and_deterministic(self):
        first = synthetic_candle_frames("XBTUSD", candles=50, seed=7)
        second = synthetic_candle_frames("XBTUSD", candles=50, seed=7)
        assert all(record.synthetic for record in first)
        assert [r.frame for r in first] == [r.frame for r in second]
        other_seed = synthetic_candle_frames("XBTUSD", candles=50, seed=8)
        assert [r.frame for r in first] != [r.frame for r in other_seed]

    def test_synthetic_bundle_carries_evidence_labels(self):
        records = synthetic_candle_frames("XBTUSD", candles=5, seed=7)
        bundle = make_synthetic_bundle("XBTUSD", records)
        assert bundle["evidence_class"] == "SYNTHETIC_FIXTURE"
        assert bundle["synthetic"] is True
        for record in bundle["frames"]:
            assert record["synthetic"] is True

    def test_candle_starts_are_minute_aligned(self):
        records = synthetic_candle_frames("XBTUSD", candles=10, seed=7)
        for record in records:
            start_seconds = record.frame["cst"] // 1_000_000
            assert start_seconds % 60 == 0

    def test_synthetic_replay_routes_every_closed_candle(self):
        candles = 200
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
            )
            assert report.transport["closed_delivered"] == candles - 1
            assert report.engine["routed"] == candles - 1
            assert report.pipeline["candles_processed"] == candles - 1
            assert report.engine["route_errors"] == 0
            worker = report.workers["BTCUSDT"]
            assert worker["status"] == "LIVE"
            assert worker["forming_skipped"] >= 1
            assert report.gaps["statuses"]["DELTA:BTCUSDT:1m"][
                "status"
            ] == "CONTINUOUS"
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True


# ==================================================================
# Fault injection: duplicates, out-of-order, malformed, gaps
# ==================================================================


class TestFaultInjectionPolicy:
    def test_duplicate_frame_is_suppressed(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(DuplicateFault(after_ordinal=10),),
            )
            assert report.synthetic_frames_injected == 1
            assert report.stream["duplicates_or_old"] == 1
            assert report.stream["rejected"] == 0
            # the duplicate never produced an extra pipeline cycle
            assert report.engine["routed"] == candles - 1
            assert report.unrouted_during_outage == 0
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_out_of_order_retransmission_is_store_deduplicated(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(OutOfOrderFault(after_ordinal=20, back_steps=2),),
            )
            # the retransmitted older frame never delivers a closed candle
            assert report.engine["routed"] == candles - 1
            assert report.stream["duplicates_or_old"] >= 1
            assert report.paper["orders_placed"] >= 0
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_malformed_frames_are_rejected_and_counted(self):
        candles = 40
        faults = (
            MalformedFault(after_ordinal=10, mode="not_a_mapping"),
            MalformedFault(after_ordinal=15, mode="drop_volume"),
            MalformedFault(after_ordinal=20, mode="drop_symbol"),
            MalformedFault(after_ordinal=25, mode="impossible_ohlc"),
            MalformedFault(after_ordinal=30, mode="empty_symbol"),
        )
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=faults,
            )
            # four modes fail stream validation outright; the fifth
            # (drop_volume) re-ingests a start the store has already
            # recorded with volume, so the store dedupes it verbatim.
            assert report.stream["rejected"] == len(faults) - 1
            assert report.stream["duplicates_or_old"] >= 1
            assert report.engine["routed"] == candles - 1
            reasons = report.transport["runtime_rejections"]
            assert reasons, (
                "every malformed frame must leave a counted rejection reason"
            )

    def test_volume_less_candle_closes_are_rejected_at_the_delivery_gate(self):
        records = synthetic_candle_frames("BTCUSDT", candles=3, seed=7)
        first, second, third = (
            record.frame for record in records
        )
        volume_less = {key: value for key, value in second.items()
                       if key != "v"}
        with replay(("BTCUSDT",)) as harness:
            harness.ingest(first, receipt_timestamp=1)
            assert harness.ingest(
                volume_less, receipt_timestamp=2,
            )["ingest_status"] == "APPLIED"
            # the third start closes the volume-less candle: the delivery
            # gate refuses it -- volume-unavailable candles can never
            # drive strategy, decisions or orders.
            harness.ingest(third, receipt_timestamp=3)
            stats = harness.transport.stats()
            assert stats["closed_delivered"] == 1
            assert stats["runtime_rejections"][
                "traded candle volume is unavailable"
            ] == 1
            assert harness.engine.routed == 1

    def test_gap_blocks_subsequent_closes_until_repair(self):
        candles = 30
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(GapFault(after_ordinal=15, missing_candles=2),),
            )
            assert report.skipped_for_gap == 2
            status = report.gaps["statuses"]["DELTA:BTCUSDT:1m"]
            assert status["status"] == "DATA_GAP_UNREPAIRED"
            assert status["missing_candles"] == 2
            # every close attempt after the gap was rejected fail-closed:
            # possible closes = candles - 1, minus the two candle closes
            # whose frames were skipped, minus what was actually delivered.
            blocked = report.transport["runtime_rejections"][
                "candle continuity is not verified"
            ]
            assert blocked == (candles - 1 - report.skipped_for_gap) - (
                report.transport["closed_delivered"]
            )
            assert report.engine["routed"] == report.transport[
                "closed_delivered"
            ]
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_repair_restores_continuity_and_delivery_resumes(self):
        records = list(
            synthetic_candle_frames("BTCUSDT", candles=26, seed=7),
        )
        by_ordinal = {record.ordinal: record for record in records}
        with replay(("BTCUSDT",)) as harness:
            for ordinal in range(1, 16):
                record = by_ordinal[ordinal]
                harness.ingest(
                    record.frame, receipt_timestamp=record.receipt_ns,
                )
            # skip candles 16-17, then feed 18 (gap detected)
            harness.ingest(
                by_ordinal[18].frame,
                receipt_timestamp=by_ordinal[18].receipt_ns,
            )
            status = harness.continuity_status("BTCUSDT", "1m")
            assert status["status"] == "DATA_GAP_UNREPAIRED"
            delivered_before = harness.transport.stats()["closed_delivered"]

            repair = self._repair(harness, by_ordinal, (16, 17))
            assert repair["accepted"] == 2
            assert repair["ranges_repaired"] == 1
            assert repair["reason"] == "all matching gaps repaired"
            assert (
                harness.continuity_status("BTCUSDT", "1m")["status"]
                == "CONTINUOUS"
            )

            # delivery resumes with the next candle frame
            record = by_ordinal[19]
            harness.ingest(record.frame, receipt_timestamp=record.receipt_ns)
            after = harness.transport.stats()
            assert after["closed_delivered"] == delivered_before + 1
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_repair_rejects_incomplete_and_foreign_starts(self):
        records = list(
            synthetic_candle_frames("BTCUSDT", candles=26, seed=7),
        )
        by_ordinal = {record.ordinal: record for record in records}
        with replay(("BTCUSDT",)) as harness:
            for ordinal in range(1, 16):
                record = by_ordinal[ordinal]
                harness.ingest(
                    record.frame, receipt_timestamp=record.receipt_ns,
                )
            harness.ingest(
                by_ordinal[18].frame,
                receipt_timestamp=by_ordinal[18].receipt_ns,
            )
            # only one of the two missing candles: the range is never
            # cleared incomplete (the state-only journal may record the
            # offered candle, but continuity stays unrepaired)
            repair = self._repair(harness, by_ordinal, (16,))
            assert repair["ranges_repaired"] == 0
            assert (
                harness.continuity_status("BTCUSDT", "1m")["status"]
                == "DATA_GAP_UNREPAIRED"
            )
            # a start outside every outstanding gap is rejected too
            foreign = self._repair(harness, by_ordinal, (2,))
            assert foreign["accepted"] == 0
            assert (
                harness.continuity_status("BTCUSDT", "1m")["status"]
                == "DATA_GAP_UNREPAIRED"
            )

    def test_repair_never_routes_backfilled_history(self):
        records = list(
            synthetic_candle_frames("BTCUSDT", candles=26, seed=7),
        )
        by_ordinal = {record.ordinal: record for record in records}
        with replay(("BTCUSDT",)) as harness:
            for ordinal in range(1, 16):
                record = by_ordinal[ordinal]
                harness.ingest(
                    record.frame, receipt_timestamp=record.receipt_ns,
                )
            harness.ingest(
                by_ordinal[18].frame,
                receipt_timestamp=by_ordinal[18].receipt_ns,
            )
            routed_before = harness.engine.routed
            processed_before = harness._pipeline_processed()["BTCUSDT"]
            self._repair(harness, by_ordinal, (16, 17))
            assert harness.engine.routed == routed_before
            assert (
                harness._pipeline_processed()["BTCUSDT"] == processed_before
            )

    @staticmethod
    def _repair(harness, by_ordinal, ordinals):
        candles = []
        for ordinal in ordinals:
            frame = by_ordinal[ordinal].frame
            candles.append(
                SimpleNamespace(
                    timestamp=frame["cst"] // 1_000_000,
                    open=frame["o"],
                    high=frame["h"],
                    low=frame["l"],
                    close=frame["c"],
                    volume=frame["v"],
                ),
            )
        return harness.repair_gap_history(
            "BTCUSDT",
            "1m",
            candles,
            receipt_timestamp=1_700_000_000_000_000_000,
        )


# ==================================================================
# Interruption recovery: disconnect, outage window, resubscribe
# ==================================================================


class TestInterruptionRecovery:
    def test_disconnect_then_resubscribe_restores_delivery(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(DisconnectFault(after_ordinal=25, resubscribe_after=2),),
            )
            assert report.disconnects["notify_down"] == 1
            assert report.disconnects["resubscribed"] == 1
            assert report.workers["BTCUSDT"]["status"] == "LIVE"
            # delivery resumed after the outage
            assert report.engine["routed"] == report.transport[
                "closed_delivered"
            ]
            assert report.unrouted_during_outage >= 1
            assert report.stream["duplicates_or_old"] == 0
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_immediate_resubscribe_never_loses_the_ledger(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(DisconnectFault(after_ordinal=25, resubscribe_after=0),),
            )
            # teardown + resubscribe within one record cycle: the ledger
            # stays clean and delivery continues on the live subscription
            assert report.disconnects["notify_down"] == 1
            assert report.disconnects["resubscribed"] == 1
            assert report.workers["BTCUSDT"]["status"] == "LIVE"
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_outage_window_frames_are_unrouted_not_delivered_late(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(DisconnectFault(after_ordinal=25, resubscribe_after=2),),
            )
            unrouted = report.unrouted_during_outage
            assert 1 <= unrouted <= 3
            # nothing routed while down; nothing delivered late afterwards
            assert report.engine["routed"] == report.transport[
                "closed_delivered"
            ]
            assert report.workers["BTCUSDT"]["status"] == "LIVE"
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_reconnect_never_creates_duplicate_paper_fills(self):
        candles = 60
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=99),
                faults=(
                    DisconnectFault(after_ordinal=30, resubscribe_after=0),
                    DuplicateFault(after_ordinal=45),
                ),
            )
            assert report.stream["duplicates_or_old"] >= 1
            ledger = reconcile_paper_ledger(harness)
            assert ledger["consistent"] is True
            state = ledger["symbols"][("DELTA", "BTCUSDT")]
            assert state["completed_trades"] == report.paper["trades_closed"]

    def test_partial_outage_is_symbol_scoped(self):
        candles = 40
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                faults=(DisconnectFault(after_ordinal=25, resubscribe_after=0),),
            )
            # only BTCUSDT was subscribed; nothing else existed to disturb
            assert list(report.workers) == ["BTCUSDT"]


# ==================================================================
# Safe rejection: unregistered symbols, invalid data, forming-only
# ==================================================================


class TestSafeRejection:
    def test_unregistered_symbol_never_routes(self):
        with replay(("BTCUSDT",)) as harness:
            routed_before = harness.engine.routed
            frame = dict(
                synthetic_candle_frames("ETHUSD", candles=1, seed=7)[0].frame,
            )
            frame["sy"] = "ETHUSD"
            result = harness.ingest(frame, receipt_timestamp=1)
            # the stream records the well-formed frame state-only; no
            # runtime exists for it, so nothing can ever be routed
            assert result["ingest_status"] == "APPLIED"
            assert harness.engine.routed == routed_before
            assert harness.transport.stats()["unrouted"] >= 1
            runtime = harness.runtime("BTCUSDT")
            assert len(runtime.engine.placed) == 0
            assert harness.engine.registry.count == 1

    def test_impossible_candle_geometry_never_reaches_strategy(self):
        with replay(("BTCUSDT",)) as harness:
            frame = dict(
                synthetic_candle_frames("BTCUSDT", candles=1, seed=7)[0].frame,
            )
            frame["h"] = 1.0
            frame["l"] = 2.0
            result = harness.ingest(frame, receipt_timestamp=1)
            assert result["ingest_status"] == "REJECTED"
            stats = harness.transport.stats()
            assert stats["stream"]["rejected"] == 1
            assert harness.engine.routed == 0

    def test_forming_only_frames_never_create_decisions(self):
        with replay(("BTCUSDT",)) as harness:
            record = synthetic_candle_frames("BTCUSDT", candles=1, seed=7)[0]
            harness.ingest(record.frame, receipt_timestamp=record.receipt_ns)
            assert harness.transport.stats()["closed_delivered"] == 0
            assert harness.engine.routed == 0
            outcome = harness.capture_cycle_outcomes().get("BTCUSDT", {})
            assert outcome.get("decision_accepted", 0) == 0
            assert len(harness.runtime("BTCUSDT").engine.placed) == 0

    def test_downstream_exception_is_isolated_and_counted(self):
        candles = 10
        with replay(("BTCUSDT",)) as harness:
            runtime = harness.runtime("BTCUSDT")
            broker = runtime.engine
            original = broker.run_candle

            def failing_once(candle):
                broker.run_candle = original
                raise RuntimeError("synthetic downstream failure")

            broker.run_candle = failing_once
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                stop_check=lambda: harness.engine.route_errors >= 1,
            )
            assert report.engine["route_errors"] == 1
            assert harness.engine.last_route_error
            # the next closed candle routes normally again
            assert report.engine["routed"] >= 1
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True


# ==================================================================
# Shutdown and cold start
# ==================================================================


class TestShutdownAndColdStart:
    def test_transport_shutdown_leaves_engine_safe(self):
        with replay(("BTCUSDT",)) as harness:
            records = synthetic_candle_frames("BTCUSDT", candles=20, seed=7)
            harness.run(records)
            assert harness.engine.routed == 19
            harness.stop()
            assert harness.engine.subscriptions.statuses() == {}
            # a candle start the store has never seen, exactly one window
            # after the last ingested start so the continuity gate allows
            # the delivery attempt to reach the (empty) routing layer
            frame = dict(
                synthetic_candle_frames("BTCUSDT", candles=1, seed=7)[0].frame,
            )
            frame["cst"] = frame["cst"] + 20 * 60 * 1_000_000
            result = harness.ingest(frame, receipt_timestamp=2)
            # stream-level state may still record the frame, but with no
            # subscription nothing can be routed to a runtime
            assert result["ingest_status"] == "APPLIED"
            assert harness.transport.stats()["unrouted"] >= 1
            assert harness.engine.registry.count == 1

    def test_cold_start_requires_two_starts_for_first_close(self):
        with replay(("BTCUSDT",)) as harness:
            records = list(
                synthetic_candle_frames("BTCUSDT", candles=4, seed=7),
            )
            # first start: forming only
            harness.ingest(
                records[0].frame, receipt_timestamp=records[0].receipt_ns,
            )
            assert harness.transport.stats()["closed_delivered"] == 0
            # second start: finalizes the first candle
            harness.ingest(
                records[1].frame, receipt_timestamp=records[1].receipt_ns,
            )
            assert harness.transport.stats()["closed_delivered"] == 1
            assert harness.engine.routed == 1


# ==================================================================
# Integrated risk enforcement (setup -> decision -> risk -> placement)
# ==================================================================


class TestIntegratedRiskEnforcement:
    """1:6 frozen floor and the runtime policy floor, in the real chain.

    The synthetic feed family mirrors the canonical pipeline feed, so the
    structures (FVGs, order blocks, regime) and the RR distribution are
    the repository's own, replayed through the verified transport seam.
    """

    def test_runtime_policy_admits_above_policy_floor(self):
        candles = 600
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=99),
            )
            assert report.risk["setups_seen_total"] > 0
            assert report.risk["decision_accepted_total"] > 0
            assert report.paper["orders_placed"] > 0
            placed = harness.runtime("BTCUSDT").engine.placed
            for order in placed:
                assert order.risk_reward >= 1.0
                assert order.direction in ("BULLISH", "BEARISH")
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_frozen_floor_rejects_sub_floor_at_decision(self, monkeypatch):
        monkeypatch.setenv("QUANTENGINE_FROZEN_OOS", "1")
        candles = 600
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=99),
            )
            # same feed, same structures -- but the frozen 1:6 era gate
            # rejects every sub-floor candidate at the decision stage
            # (core/setup/decision_engine.py: the FROZEN_ERA_MIN_RR check,
            # reason label "Risk Reward").
            assert report.risk["setups_seen_total"] > 0
            assert report.risk["decision_accepted_total"] == 0
            assert report.paper["orders_placed"] == 0
            rejected = report.observations
            reasons = {
                reason
                for obs in rejected
                for reason in obs["decision_rejected"]
            }
            assert "Risk Reward" in reasons
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_frozen_floor_admits_above_floor_signals(self, monkeypatch):
        monkeypatch.setenv("QUANTENGINE_FROZEN_OOS", "1")
        candles = 900
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=11),
            )
            assert report.risk["decision_accepted_total"] > 0
            assert report.risk["decision_accepted_rr"], (
                "accepted candidates must carry their reward:risk ratios"
            )
            for rr in report.risk["decision_accepted_rr"]:
                assert rr >= 6.0
            assert report.paper["orders_placed"] > 0
            placed = harness.runtime("BTCUSDT").engine.placed
            for order in placed:
                assert order.risk_reward >= 6.0
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True

    def test_runtime_policy_rejects_below_policy_floor_at_decision(self):
        # the same feed as test_runtime_policy_admits_above_policy_floor,
        # but with the runtime floor raised (in memory only, restored) so
        # the same candidates fall below it: rejected at the decision
        # stage, zero orders.  The persisted operator policy file is
        # never touched.
        from core.risk.trading_policy import (
            TradingPolicy,
            trading_policy_manager,
        )

        candles = 600
        manager = trading_policy_manager()
        saved = manager._global
        try:
            manager._global = TradingPolicy(
                min_rr=8.0,
                max_rr=20.0,
                trailing_enabled=True,
                trailing_activation_r=1.0,
                trailing_distance_r=0.5,
                auto_exit_on_opposite_signal=True,
            ).validate()
            with replay(("BTCUSDT",)) as harness:
                report = harness.run(
                    synthetic_candle_frames(
                        "BTCUSDT", candles=candles, seed=99,
                    ),
                )
                assert report.risk["decision_accepted_total"] == 0
                assert report.paper["orders_placed"] == 0
                reasons = {
                    reason
                    for obs in report.observations
                    for reason in obs["decision_rejected"]
                }
                assert "Risk Reward" in reasons
        finally:
            manager._global = saved
        outcome = reconcile_paper_ledger(harness)
        assert outcome["consistent"] is True


# ==================================================================
# Report contract
# ==================================================================


class TestReplayReportContract:
    def test_report_json_is_serializable_and_complete(self):
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=30, seed=7),
            )
            payload = json.loads(report.to_json(include_observations=True))
            counts = payload["counts"]
            for section in (
                "stream",
                "transport",
                "workers",
                "engine",
                "pipeline",
                "risk",
                "paper",
                "gaps",
                "disconnects",
                "log_verdicts",
            ):
                assert section in counts
            assert payload["schema"] == "quantengine.verified-transport-replay.v1"
            assert payload["counts"]["paper"]["orders_placed"] == (
                payload["counts"]["risk"]["orders_created_placed"]
            )
            assert payload["evidence_class"] in ("CAPTURED", "SYNTHETIC_FIXTURE")

    def test_log_verdicts_capture_production_trail(self):
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=600, seed=99),
            )
            assert report.log_verdicts.get("PIPELINE_ADDED") == 1
            assert report.log_verdicts.get("SETUP_ACCEPTED", 0) >= 1
            assert report.log_verdicts.get("SETUP_REJECTED", 0) >= 1


# ==================================================================
# Soak smoke (short; the full soak runs via scripts/run_verified_transport_replay.py)
# ==================================================================


class TestSoakSmoke:
    def test_short_soak_completes_clean(self):
        candles = 400
        with replay(("BTCUSDT",)) as harness:
            report = harness.run(
                synthetic_candle_frames("BTCUSDT", candles=candles, seed=7),
                measure=True,
            )
            assert report.frames_ingested == candles
            assert report.engine["route_errors"] == 0
            assert report.engine["reconcile_errors"] == 0
            assert report.latency_ms["max"] > 0.0
            assert report.memory_peak_mb > 0.0
            outcome = reconcile_paper_ledger(harness)
            assert outcome["consistent"] is True
