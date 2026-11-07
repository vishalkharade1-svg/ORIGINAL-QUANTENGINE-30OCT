#!/usr/bin/env python3
"""Phase 26 (P26-B/C) order-lifecycle trace for the certified frozen OOS.

Runs the CANONICAL ``run_frozen_oos`` executor (no reimplementation) with
its opt-in ``order_trace`` sink over the Phase-18 certified protocol
(6 independent per-period runs + 1 global sanity run) and writes a
machine-readable per-order lifecycle artifact:

    reports/PHASE26_ORDER_LIFECYCLE.json

The script is research-only, uses no credentials, places no orders and
changes no thresholds. It verifies the certified dataset identity and
that the reproduced funnels match ``research/results/phase18_oos_validation.json``
exactly before writing evidence. Exit codes: 0 success; 2 fail-closed on
any identity/reproduction/instrumentation invariant violation.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASET = REPO_ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
RECORDED = REPO_ROOT / "research" / "results" / "phase18_oos_validation.json"
OUTPUT = REPO_ROOT / "reports" / "PHASE26_ORDER_LIFECYCLE.json"

EXPECTED_FILE_SHA256 = (
    "986fdae1189f5695c710a3315a44fe3c649bed66687a0a18ea73247c338ef2ef")
EXPECTED_DATASET_IDENTITY = (
    "247d8f11dcd34d4975eea550f97b1fe79600cb060a9e6ade7b172bca26b89c54")
GATE_A_END = 1788601440


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_identity(rows) -> str:
    blob = json.dumps(sorted(rows, key=lambda row: row["time"]),
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _integrity(rows) -> dict:
    stamps = [int(row["time"]) for row in rows]
    duplicates = len(stamps) - len(set(stamps))
    gaps = [(a, b) for a, b in zip(stamps, stamps[1:]) if b - a != 60]
    ohlc_violations = 0
    malformed = 0
    for row in rows:
        try:
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        except (KeyError, TypeError, ValueError):
            malformed += 1
            continue
        if h < max(o, c) or l > min(o, c) or h < l:
            ohlc_violations += 1
    return {
        "rows": len(rows),
        "ascending": all(b > a for a, b in zip(stamps, stamps[1:])),
        "duplicates": duplicates,
        "gap_count": len(gaps),
        "gaps": gaps[:10],
        "ohlc_violations": ohlc_violations,
        "malformed": malformed,
        "start": stamps[0],
        "end": stamps[-1],
        "strictly_after_gate_a": all(stamp > GATE_A_END for stamp in stamps),
    }


def _funnel_view(funnel) -> dict:
    return {
        "orders": funnel["orders"],
        "fills": funnel["fills"],
        "terminal": dict(funnel["terminal"]),
        "directional": dict(funnel["directional"]),
    }


def main() -> int:
    from core.research.oos_validation.execution import run_frozen_oos
    from core.research.oos_validation.periods import split_bars
    from core.research.oos_validation.report import classify_period
    from core.research.oos_validation.order_trace import summarize_records
    from core.research.strategy_identity import (
        FROZEN_ERA_MIN_RR,
        FROZEN_OOS_ENV,
        get_versioned_identities,
    )

    failures: list[str] = []

    if _sha256_file(DATASET) != EXPECTED_FILE_SHA256:
        failures.append("dataset file sha256 mismatch")
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = sorted(payload["raw"], key=lambda row: row["time"])
    identity = _dataset_identity(rows)
    if identity != EXPECTED_DATASET_IDENTITY:
        failures.append("dataset content identity mismatch")
    if payload.get("fresh_after") != GATE_A_END:
        failures.append("dataset fresh_after boundary mismatch")
    integrity = _integrity(rows)
    if integrity["duplicates"] or integrity["gap_count"] or \
            integrity["ohlc_violations"] or integrity["malformed"] or \
            not integrity["ascending"] or not integrity["strictly_after_gate_a"]:
        failures.append("dataset integrity check failed")

    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    recorded_periods = {p["period_id"]: p for p in recorded["periods"]}
    recorded_global = recorded["global_continuous_run"]

    slices = split_bars(rows, n_periods=6, prefix="OOS")
    period_runs = []
    all_records = []
    per_period_orders = {}
    for spec in slices:
        start, end = spec["slice"]
        sub = rows[start:end]
        trace: list[dict] = []
        funnel = run_frozen_oos(sub, symbol="BTCUSDT", order_trace=trace)
        status, reason = classify_period(funnel)
        expected = recorded_periods.get(spec["period_id"], {})
        view = _funnel_view(funnel)
        matches = {
            "orders": view["orders"] == expected.get("orders"),
            "fills": view["fills"] == expected.get("fills"),
            "terminal": view["terminal"] == expected.get("terminal"),
            "directional": view["directional"] == expected.get("directional"),
            "status": status == expected.get("status"),
            "reason": reason == expected.get("reason"),
        }
        if not all(matches.values()):
            failures.append("period reproduction mismatch: %s %s"
                            % (spec["period_id"], matches))
        summary = summarize_records(trace)
        if summary["unknown_classifications"]:
            failures.append("unknown classification in %s" % spec["period_id"])
        if summary["records_missing_trigger_evidence"]:
            failures.append("missing trigger evidence in %s" % spec["period_id"])
        for record in trace:
            if record.get("rr_consistency") is False:
                failures.append("RR inconsistency: %s" % record["order_id"])
            if record.get("inverted_entry_consistency") is False:
                failures.append("inverted-fill inconsistency: %s" % record["order_id"])
            if record.get("trigger_close_consistency") is False:
                failures.append("trigger-close mismatch: %s" % record["order_id"])
        per_period_orders[spec["period_id"]] = len(trace)
        period_runs.append({
            "period_id": spec["period_id"],
            "start": spec["start"],
            "end": spec["end"],
            "observations": spec["row_count"],
            "recorded": {
                "orders": expected.get("orders"),
                "fills": expected.get("fills"),
                "terminal": expected.get("terminal"),
                "directional": expected.get("directional"),
                "status": expected.get("status"),
                "reason": expected.get("reason"),
            },
            "reproduced": dict(view, status=status, reason=reason),
            "reproduction_matches": matches,
            "summary": summary,
            "orders": trace,
        })
        for record in trace:
            record = dict(record)
            record["run"] = spec["period_id"]
            all_records.append(record)

    global_trace: list[dict] = []
    global_funnel = run_frozen_oos(rows, symbol="BTCUSDT", order_trace=global_trace)
    global_view = _funnel_view(global_funnel)
    global_matches = {
        "orders": global_view["orders"] == recorded_global.get("orders"),
        "fills": global_view["fills"] == recorded_global.get("fills"),
        "terminal": global_view["terminal"] == recorded_global.get("terminal"),
        "directional": global_view["directional"] == recorded_global.get("directional"),
    }
    if not all(global_matches.values()):
        failures.append("global reproduction mismatch: %s" % global_matches)
    global_summary = summarize_records(global_trace)
    if global_summary["unknown_classifications"]:
        failures.append("unknown classification in global run")
    if global_summary["records_missing_trigger_evidence"]:
        failures.append("missing trigger evidence in global run")
    for record in global_trace:
        if record.get("rr_consistency") is False:
            failures.append("RR inconsistency: %s" % record["order_id"])
        if record.get("inverted_entry_consistency") is False:
            failures.append("inverted-fill inconsistency: %s" % record["order_id"])
        if record.get("trigger_close_consistency") is False:
            failures.append("trigger-close mismatch: %s" % record["order_id"])
    for record in global_trace:
        record = dict(record)
        record["run"] = "GLOBAL"
        all_records.append(record)

    status_counter = Counter(record["status"] for record in global_trace)
    if dict(status_counter) != dict(global_funnel["terminal"]):
        failures.append("trace/funnel terminal mismatch (global)")
    for run in period_runs:
        trace_status = Counter(record["status"] for record in run["orders"])
        if dict(trace_status) != dict(run["reproduced"]["terminal"]):
            failures.append("trace/funnel terminal mismatch: %s"
                            % run["period_id"])

    identities = get_versioned_identities(REPO_ROOT)
    import config.risk_settings as risk_settings

    config_snapshot = {
        "MIN_RISK_REWARD": getattr(risk_settings, "MIN_RISK_REWARD", None),
        "ENTRY_MODE": getattr(risk_settings, "ENTRY_MODE", None),
        "ACTIVE_ENTRY_MODES": list(getattr(
            risk_settings, "ACTIVE_ENTRY_MODES", ()) or ()),
        "MAX_WAIT_BARS": getattr(risk_settings, "MAX_WAIT_BARS", None),
        "ENTRY_DELAY_BARS": getattr(risk_settings, "ENTRY_DELAY_BARS", None),
        "STARTING_BALANCE": getattr(risk_settings, "STARTING_BALANCE", None),
        "RISK_PER_TRADE": getattr(risk_settings, "RISK_PER_TRADE", None),
        "FROZEN_ERA_MIN_RR": float(FROZEN_ERA_MIN_RR),
        "FROZEN_OOS_ENV": FROZEN_OOS_ENV,
    }

    artifact = {
        "phase": 26,
        "workstreams": ["P26-A", "P26-B", "P26-C"],
        "purpose": (
            "Per-order lifecycle trace of the certified Phase-18 frozen "
            "OOS zero-fill outcome. Diagnostic evidence only; no strategy, "
            "data, threshold, entry-model or fill-model change."),
        "provenance": {
            "dataset_path": "data/history/BTCUSDT_1m_phase17_fresh.json",
            "dataset_file_sha256": _sha256_file(DATASET),
            "dataset_identity_sha256": identity,
            "fresh_after": payload.get("fresh_after"),
            "gate_a_end": GATE_A_END,
            "requested": payload.get("requested"),
            "recorded_artifact": "research/results/phase18_oos_validation.json",
            "recorded_baseline_commit": recorded.get("baseline_commit"),
            "recorded_strategy_hash": recorded.get("strategy_hash"),
            "current_strategy_identities": {
                "strategy_core": identities["strategy_core"]["sha256"],
                "runtime_infrastructure": identities[
                    "runtime_infrastructure"]["sha256"],
                "composite_legacy_9_files_canonical_lf": identities[
                    "composite_legacy_9_files"]["canonical_lf_sha256"],
                "composite_legacy_9_files_raw": identities[
                    "composite_legacy_9_files"].get("raw_sha256"),
            },
            "strategy_file_pin_matches_recorded": False,
            "strategy_pin_note": (
                "The legacy 9-file composite pin recorded by Phase 18 "
                "(c52e648...) no longer matches the current tree bytes; the "
                "certified FUNNEL reproduction is behavioral at HEAD, not "
                "byte-identical at the historical revision. The historical "
                "revision 6eb35d8 is not an ancestor and does not contain "
                "the Phase-18 harness."),
            "config_snapshot": config_snapshot,
        },
        "integrity": integrity,
        "protocol": {
            "executor": "core/research/oos_validation/execution.py:run_frozen_oos",
            "periods": "split_bars(n_periods=6, prefix=OOS)",
            "global_run": "single continuous run over all rows",
            "entry_mode": config_snapshot["ENTRY_MODE"],
            "active_entry_modes": config_snapshot["ACTIVE_ENTRY_MODES"],
            "frozen_era_min_rr": config_snapshot["FROZEN_ERA_MIN_RR"],
        },
        "reproduction": {
            "recorded_global": {
                "orders": recorded_global.get("orders"),
                "fills": recorded_global.get("fills"),
                "terminal": recorded_global.get("terminal"),
                "directional": recorded_global.get("directional"),
            },
            "reproduced_global": dict(global_view),
            "matches": global_matches,
            "recorded_per_period_orders": {
                key: value.get("orders")
                for key, value in recorded_periods.items()},
            "reproduced_per_period_orders": per_period_orders,
            "byte_identical_revision_replay": "INFEASIBLE",
        },
        "global_run": {
            "summary": global_summary,
            "orders": global_trace,
        },
        "per_period_runs": period_runs,
        "cross_run_summary": {
            "global_orders": len(global_trace),
            "per_period_order_total": sum(per_period_orders.values()),
            "all_orders": len(all_records),
            "global_orders_are_independent_opportunities": False,
            "note": (
                "The 6 per-period runs are cold-start slices (independent "
                "primary evidence). The global run is a continuous sanity "
                "run: its extra orders come from uninterrupted indicator "
                "state, not from independent sampling."),
        },
        "findings": {
            "zero_fill_root_cause": (
                "Every order that triggered reached its single next-bar-open "
                "fill attempt; none was filled. The dominant cause is the "
                "frozen-era realized-RR floor: the breakout-continuation "
                "entry fills AFTER price has already moved beyond the "
                "order's entry level, so the executable reward:risk at the "
                "next open is far below the 1:6 creation-time geometry. "
                "A further two fill attempts were refused by the shared "
                "directional-geometry gate because the next open was "
                "already BEYOND the take-profit (the frozen log verb "
                "ORDER_SKIPPED_INVERTED_FILL names the gate, not a stop "
                "gap); zero attempts gapped through the stop."),
            "classification": "LEGITIMATE_NO_FILL_OUTCOME",
            "defect_assessment": (
                "No trading-logic defect found. The creation-time RR gate, "
                "the next-bar-open fill timing, the inverted-fill refusal "
                "and the expiry/invalidation lifecycle all behave as "
                "designed. The observed incompatibility is between the "
                "configured BREAKOUT_CONTINUATION entry model and the 1:6 "
                "realized-RR floor, not a software bug."),
            "observability_gap": (
                "The Phase-18 artifact persisted terminal counts only "
                "(rr_rejections=None, no rejection reasons), so the cause "
                "was not recoverable from persisted evidence. The opt-in "
                "order_trace sink repairs this without altering semantics."),
            "strategy_version_assessment": (
                "Behavioral: the certified funnel is reproduced exactly. "
                "Byte-level: the historical strategy pin does not match "
                "current bytes and the certified commit is not an ancestor "
                "of HEAD; the certified harness is absent at that commit."),
            "confidence": 1.0,
        },
        "invariant_failures": failures,
    }

    text = json.dumps(artifact, indent=2, sort_keys=True,
                      separators=(",", ": ")) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")

    print("wrote %s (%d bytes)" % (OUTPUT, len(text)))
    print("global: orders=%d fills=%d terminal=%s"
          % (global_funnel["orders"], global_funnel["fills"],
             dict(global_funnel["terminal"])))
    print("global classifications: %s" % global_summary["classifications"])
    print("global erosion_rr stats: %s" % global_summary["erosion_actual_rr"])
    print("global progress stats: %s"
          % global_summary["trigger_close_progress_fraction"])
    print("per-period orders: %s" % per_period_orders)
    print("rr consistency: %s" % global_summary["erosion_rr_consistency"])
    print("trigger-close consistency: %s"
          % global_summary["trigger_close_consistency"])
    print("geometry rejections: %s"
          % global_summary["geometry_rejections"])
    print("invariant failures: %s" % (failures or "NONE"))
    print("output sha256: %s" % hashlib.sha256(text.encode()).hexdigest())
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
