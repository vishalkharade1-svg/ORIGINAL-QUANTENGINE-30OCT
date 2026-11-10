"""Phase 26 lifecycle instrumentation and funding-evidence regression tests.

Locks the observability repair without changing frozen semantics:
the opt-in trace must not alter the funnel, every certified order must
carry precise lifecycle evidence, and the aligned funding recapture must
bind to the frozen datasets with a closed head gap.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.research.oos_validation.execution import run_frozen_oos
from core.research.oos_validation.order_trace import (
    LogCapture,
    _geometry_side,
    classify_order,
    parse_lifecycle_event,
    summarize_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
LIFECYCLE = ROOT / "reports" / "PHASE26_ORDER_LIFECYCLE.json"
REEVALUATION = ROOT / "reports" / "PHASE26_OOS_REEVALUATION.json"
RAW_FUNDING = ROOT / "reports" / "evidence" / "phase26" / "raw_funding_evidence.json"
P26_BOUND_P18 = (ROOT / "reports" / "evidence" / "phase26"
                 / "btcusdt_funding_bound_to_phase18.json")
P26_BOUND_OOS = (ROOT / "reports" / "evidence" / "phase26"
                 / "btcusdt_funding_bound_to_oos.json")
P25_BOUND_P18 = (ROOT / "reports" / "evidence" / "phase25"
                 / "btcusdt_funding_bound_to_phase18.json")


def _rows():
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = sorted(payload["raw"], key=lambda row: row["time"])
    return rows


def test_parse_lifecycle_event_reads_frozen_log_format():
    event = parse_lifecycle_event(
        "ORDER_SKIPPED_RR_EROSION setup_id=-1m-BEARISH-OB-898 "
        "order_id=-1m-BEARISH-OB-898-ORDER-1 actual_rr=0.15027322404371585 "
        "min_rr=6.00")
    assert event["verb"] == "ORDER_SKIPPED_RR_EROSION"
    assert event["fields"]["actual_rr"] == 0.15027322404371585
    assert event["fields"]["min_rr"] == 6.0
    invalidated = parse_lifecycle_event(
        "ORDER_INVALIDATED setup_id=s order_id=o created_bar=5991 "
        "eligible_from_bar=5992 invalidated_bar=6017 "
        "reason=bullish structural stop (OB low) breached price=78894.5 "
        "invalidation_level=79045.00")
    assert invalidated["fields"]["reason"] == \
        "bullish structural stop (OB low) breached"
    assert invalidated["fields"]["invalidated_bar"] == 6017
    assert parse_lifecycle_event("unrelated message") is None


def test_geometry_side_distinguishes_stop_from_target_overshoot():
    assert _geometry_side("BEARISH", 79000.0, 79600.0, 78800.0) == "VALID"
    assert _geometry_side("BEARISH", 79650.0, 79600.0, 78800.0) == "BEYOND_STOP"
    assert _geometry_side("BEARISH", 78700.0, 79600.0, 78800.0) == "BEYOND_TARGET"
    assert _geometry_side("BULLISH", 79050.0, 79000.0, 79600.0) == "VALID"
    assert _geometry_side("BULLISH", 78900.0, 79000.0, 79600.0) == "BEYOND_STOP"
    assert _geometry_side("BULLISH", 79700.0, 79000.0, 79600.0) == "BEYOND_TARGET"


def test_classification_uses_status_and_geometry():
    assert classify_order(
        "EXPIRED", ["BREAKOUT_TRIGGER", "ORDER_SKIPPED_RR_EROSION"]) == \
        "TRIGGERED_REJECTED_RR_EROSION"
    assert classify_order(
        "INVALIDATED",
        ["BREAKOUT_TRIGGER", "ORDER_SKIPPED_RR_EROSION"]) == \
        "TRIGGERED_REJECTED_RR_EROSION_THEN_INVALIDATED"
    assert classify_order(
        "EXPIRED",
        ["BREAKOUT_TRIGGER", "ORDER_SKIPPED_INVERTED_FILL"],
        "BEYOND_TARGET") == "TRIGGERED_REJECTED_FILL_BEYOND_TARGET"
    assert classify_order(
        "EXPIRED",
        ["BREAKOUT_TRIGGER", "ORDER_SKIPPED_INVERTED_FILL"],
        "BEYOND_STOP") == "TRIGGERED_REJECTED_FILL_BEYOND_STOP"
    assert classify_order("EXPIRED", []) == "EXPIRED_WITHOUT_TRIGGER"
    assert classify_order("INVALIDATED", []) == "INVALIDATED_BEFORE_TRIGGER"


def test_log_capture_restores_root_logger():
    root = logging.getLogger()
    before = root.level
    capture = LogCapture().start()
    logging.getLogger("phase26.test").info("ORDER_CREATED order_id=x")
    messages = capture.stop()
    assert any("ORDER_CREATED" in message for message in messages)
    assert root.level == before


def test_trace_preserves_funnel_and_classifies_every_order():
    rows = _rows()
    plain = run_frozen_oos(rows, symbol="BTCUSDT")
    trace: list[dict] = []
    traced = run_frozen_oos(rows, symbol="BTCUSDT", order_trace=trace)

    assert traced == plain
    assert traced["orders"] == 32
    assert traced["fills"] == 0
    assert traced["terminal"] == {"EXPIRED": 30, "INVALIDATED": 2}

    summary = summarize_records(trace)
    assert summary["orders"] == 32
    assert summary["triggered_orders"] == 32
    assert summary["fill_attempts"] == 32
    assert summary["rr_erosion_skips"] == 30
    assert summary["inverted_fill_skips"] == 2
    assert summary["geometry_rejections"] == {
        "beyond_stop": 0, "beyond_target": 2}
    assert summary["classifications"] == {
        "TRIGGERED_REJECTED_FILL_BEYOND_TARGET": 2,
        "TRIGGERED_REJECTED_RR_EROSION": 28,
        "TRIGGERED_REJECTED_RR_EROSION_THEN_INVALIDATED": 2,
    }
    assert summary["unknown_classifications"] == []
    assert summary["records_missing_trigger_evidence"] == []
    assert summary["erosion_rr_consistency"] == {
        "checked": 30, "consistent": 30, "all_consistent": True}
    assert summary["trigger_close_consistency"] == {
        "checked": 32, "consistent": 32, "all_consistent": True}
    assert summary["erosion_actual_rr"]["max"] < 6.0
    for record in trace:
        assert record["evidence_refs"]
        assert record["entry_execution"] == "NEXT_BAR_OPEN"
        assert record["lifecycle_verbs"]


def test_phase26_lifecycle_artifact_is_complete():
    artifact = json.loads(LIFECYCLE.read_text(encoding="utf-8"))
    assert artifact["invariant_failures"] == []
    assert artifact["reproduction"]["matches"] == {
        "orders": True, "fills": True, "terminal": True, "directional": True}
    assert artifact["global_run"]["summary"]["classifications"] == {
        "TRIGGERED_REJECTED_FILL_BEYOND_TARGET": 2,
        "TRIGGERED_REJECTED_RR_EROSION": 28,
        "TRIGGERED_REJECTED_RR_EROSION_THEN_INVALIDATED": 2,
    }
    per_period = {run["period_id"]: run["reproduced"]["orders"]
                  for run in artifact["per_period_runs"]}
    assert per_period == {"OOS_01": 2, "OOS_02": 0, "OOS_03": 2,
                          "OOS_04": 3, "OOS_05": 8, "OOS_06": 0}
    assert all(run["reproduction_matches"]["orders"]
               for run in artifact["per_period_runs"])
    assert artifact["findings"]["classification"] == "LEGITIMATE_NO_FILL_OUTCOME"


def test_phase26_funding_recapture_closes_head_gap():
    raw = json.loads(RAW_FUNDING.read_text(encoding="utf-8"))
    series = raw["series"]
    assert series["strictly_hourly"] is True
    assert series["head_covered"] is True
    assert series["head_pad_seconds"] > 0
    assert series["event_count"] == 529
    assert series["first_event_utc"] == "2026-09-05T00:00:00Z"

    reevaluation = json.loads(REEVALUATION.read_text(encoding="utf-8"))
    recovered = reevaluation["funding_evidence"]["recovered_head_settlements"]
    assert [item["utc"] for item in recovered] == [
        "2026-09-05T10:00:00Z", "2026-09-05T11:00:00Z",
        "2026-09-05T12:00:00Z", "2026-09-05T13:00:00Z",
        "2026-09-05T14:00:00Z", "2026-09-05T15:00:00Z"]
    assert reevaluation["funding_evidence"]["phase26_head_gap_seconds"] == 0

    old = json.loads(P25_BOUND_P18.read_text(encoding="utf-8"))
    old_times = {int(event["time"]) for event in old["events"]}
    assert old_times.isdisjoint(int(item["time"]) for item in recovered)
    assert int(old["events"][0]["time"]) == 1788624000


def test_phase26_funding_artifacts_bind_to_both_datasets(tmp_path):
    from research.economics.funding_evidence import load_and_verify

    dataset = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
    topup = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"

    # The Phase26 Phase18 binding was minted against the CRLF byte form.
    # GitHub's current canonical checkout is LF; reconstruct the exact
    # historical byte representation for verification without rewriting
    # either the dataset or its immutable evidence record.
    phase18_lf = dataset.read_bytes()
    phase18_crlf = phase18_lf.replace(b"\\r\\n", b"\\n").replace(b"\\n", b"\\r\\n")
    phase18_historical_bytes = tmp_path / "phase18_historical_crlf.json"
    phase18_historical_bytes.write_bytes(phase18_crlf)

    phase18_artifact = load_and_verify(
        P26_BOUND_P18, market_data_path=phase18_historical_bytes)
    oos_artifact = load_and_verify(P26_BOUND_OOS, market_data_path=topup)
    assert phase18_artifact.provenance_status == "REAL"
    assert oos_artifact.provenance_status == "REAL"
    assert phase18_artifact.funding_evidence_sha256 == \
        oos_artifact.funding_evidence_sha256
    assert min(event["time"] for event in phase18_artifact.events) == 1788566400


def test_phase26_reevaluation_keeps_gates_closed():
    artifact = json.loads(REEVALUATION.read_text(encoding="utf-8"))
    assert artifact["strategy_logic_changed"] is False
    assert artifact["thresholds_changed"] is False
    assert artifact["entry_model_changed"] is False
    assert artifact["fill_model_changed"] is False
    assert artifact["certified_protocol_reproduction"]["all_match"] is True
    assert artifact["funding_evidence"]["head_gap_repaired"] is True
    assert artifact["funding_evidence"]["phase26_head_gap_seconds"] == 0
    assert artifact["funding_evidence"]["phase25_head_gap_seconds"] == 22500
    assert artifact["economics_status"]["fills"] == 0
    assert artifact["economics_status"]["cost_status"] == \
        "NOT_APPLICABLE_NO_FILLS"
    assert artifact["economics_status"]["funding_status"] == \
        "NOT_APPLICABLE_NO_FILLS"
    for scenario in artifact["cost_ladders"]:
        assert scenario["attribution"] == "NOT_APPLICABLE_NO_FILLS"
        assert scenario["applied_to_oos"] is False
    assert artifact["verdict"]["final_decision"] == "OOS_BLOCKED"
    assert artifact["verdict"]["edge_status"] == "EDGE NOT ESTABLISHED"
    assert artifact["verdict"]["release_gate"] == "HOLD"
    assert artifact["verdict"]["zero_fill_classification"] == \
        "LEGITIMATE_NO_FILL_OUTCOME"
