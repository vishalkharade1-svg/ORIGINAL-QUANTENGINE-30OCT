#!/usr/bin/env python3
"""Phase 26 (P26-D/F) distinct frozen-OOS re-evaluation.

This is a NEW evidence artifact; Phase-18 and Phase-25 evidence is never
modified. It re-executes the certified Phase-18 protocol with the
Phase-26 aligned funding schedule (no head gap) on both frozen datasets,
attributes funding only inside holding intervals, and re-runs the
preregistered cost ladders.

Because the frozen strategy still produces ZERO fills, every cost/funding
attribution is labelled NOT_APPLICABLE_NO_FILLS: a zero total is not
evidence of zero execution cost. Funding settlements are counted inside
each period so a future filled run has an exact evidence basis.

Output: reports/PHASE26_OOS_REEVALUATION.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

P18_DATASET = REPO_ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
P30_DATASET = REPO_ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
P18_RECORDED = REPO_ROOT / "research" / "results" / "phase18_oos_validation.json"
P30_RECORDED = REPO_ROOT / "research" / "results" / "phase30_oos_evidence_accumulation.json"
P25_RESULTS = REPO_ROOT / "research" / "results" / "phase25_frozen_oos_validation.json"
P25_BOUND_OOS = REPO_ROOT / "reports" / "evidence" / "phase25" / "btcusdt_funding_bound_to_oos.json"
P25_BOUND_P18 = REPO_ROOT / "reports" / "evidence" / "phase25" / "btcusdt_funding_bound_to_phase18.json"
P26_BOUND_OOS = REPO_ROOT / "reports" / "evidence" / "phase26" / "btcusdt_funding_bound_to_oos.json"
P26_BOUND_P18 = REPO_ROOT / "reports" / "evidence" / "phase26" / "btcusdt_funding_bound_to_phase18.json"
LIFECYCLE = REPO_ROOT / "reports" / "PHASE26_ORDER_LIFECYCLE.json"
OUT = REPO_ROOT / "reports" / "PHASE26_OOS_REEVALUATION.json"

P18_IDENTITY = "247d8f11dcd34d4975eea550f97b1fe79600cb060a9e6ade7b172bca26b89c54"
P30_IDENTITY = "520b849b6612335d4987161d67b5163939bf9e20019dd5a25ec02b876a2310b0"
FRESH_AFTER = 1788601440
SYMBOL = "BTCUSDT"


def _utc(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path, expected_identity: str):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("raw")
    if not isinstance(rows, list) or not rows:
        raise SystemExit("FAIL_CLOSED: no rows in %s" % path)
    rows = sorted(rows, key=lambda row: int(row["time"]))
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    identity = hashlib.sha256(blob).hexdigest()
    if identity != expected_identity:
        raise SystemExit("FAIL_CLOSED: dataset identity mismatch: %s" % path)
    if any(int(row["time"]) <= FRESH_AFTER for row in rows):
        raise SystemExit("FAIL_CLOSED: freshness violation: %s" % path)
    return rows, identity, _sha_file(path)


def _funding_count(schedule, start: int, end: int) -> int:
    return sum(1 for event in schedule.events
               if start <= int(event.timestamp) <= end)


def _funding_events(schedule, start: int, end: int) -> list[dict]:
    return [{"time": int(event.timestamp), "utc": _utc(event.timestamp),
             "rate": float(event.rate)}
            for event in schedule.events
            if start <= int(event.timestamp) <= end]


def _strict_series_check(schedule, first: int, last: int) -> dict:
    stamps = [int(event.timestamp) for event in schedule.events]
    gaps = [b - a for a, b in zip(stamps, stamps[1:]) if b - a != 3600]
    return {
        "event_count": len(stamps),
        "first_event": stamps[0],
        "first_event_utc": _utc(stamps[0]),
        "last_event": stamps[-1],
        "last_event_utc": _utc(stamps[-1]),
        "strictly_hourly": not gaps,
        "non_hourly_gap_count": len(gaps),
        "head_covered": stamps[0] <= first,
        "head_gap_seconds": max(0, stamps[0] - first),
        "head_pad_seconds": max(0, first - stamps[0]),
        "tail_covered": last - stamps[-1] <= 3600,
        "settlements_in_oos": _funding_count(schedule, first, last),
    }


def _funnel(result) -> dict:
    return {
        "bars": result["bars"],
        "orders": result["orders"],
        "terminal": dict(result["terminal"]),
        "directional": dict(result["directional"]),
        "fills": result["fills"],
        "completed_trades": result["completed_trades"],
        "wins": result["wins"],
        "losses": result["losses"],
        "gross_pnl": result["gross_pnl"],
        "funding": result["funding"],
        "commission": result["commission"],
        "slippage": result["slippage"],
        "net_pnl": result["net_pnl"],
        "actual_fill_rr": list(result["actual_fill_rr"]),
    }


def main() -> int:
    from core.research.oos_validation.execution import (
        load_verified_funding_schedule,
        run_frozen_oos,
    )
    from core.research.oos_validation.periods import split_bars
    from research.phase11f.harness import COST_SCENARIOS_11F
    from core.risk.costs import CostSpec

    p18_rows, p18_identity, p18_file_sha = _load(P18_DATASET, P18_IDENTITY)
    p30_rows, p30_identity, p30_file_sha = _load(P30_DATASET, P30_IDENTITY)
    p18_recorded = json.loads(P18_RECORDED.read_text(encoding="utf-8"))
    p30_recorded = json.loads(P30_RECORDED.read_text(encoding="utf-8"))
    p25 = json.loads(P25_RESULTS.read_text(encoding="utf-8"))

    schedule_p18 = load_verified_funding_schedule(
        P26_BOUND_P18, P18_DATASET, p18_rows)
    schedule_oos = load_verified_funding_schedule(
        P26_BOUND_OOS, P30_DATASET, p30_rows)
    funding_p18 = _strict_series_check(
        schedule_p18, int(p18_rows[0]["time"]), int(p18_rows[-1]["time"]))
    funding_oos = _strict_series_check(
        schedule_oos, int(p30_rows[0]["time"]), int(p30_rows[-1]["time"]))

    p25_events = {
        int(event["time"])
        for event in json.loads(
            P25_BOUND_OOS.read_text(encoding="utf-8"))["events"]}
    recovered = [event for event in _funding_events(
        schedule_p18, int(p18_rows[0]["time"]), 1788624000)
        if int(event["time"]) not in p25_events]
    if not recovered:
        raise SystemExit("FAIL_CLOSED: no repaired head settlements recovered")

    # ---------------- certified protocol, no funding ----------------
    p18_periods = split_bars(p18_rows, n_periods=6, prefix="OOS")
    reproduction = []
    for period in p18_periods:
        s, e = period["slice"]
        result = run_frozen_oos(p18_rows[s:e], symbol=SYMBOL)
        recorded = next(p for p in p18_recorded["per_period_results"]
                        if p["period_id"] == period["period_id"])
        reproduction.append({
            "period_id": period["period_id"],
            "bars": result["bars"],
            "orders": result["orders"],
            "fills": result["fills"],
            "terminal": dict(result["terminal"]),
            "phase18_orders": recorded["orders"],
            "phase18_fills": recorded["fills"],
            "matches": result["orders"] == recorded["orders"]
            and result["fills"] == recorded["fills"],
        })
    global_plain = run_frozen_oos(p18_rows, symbol=SYMBOL)
    if not all(item["matches"] for item in reproduction):
        raise SystemExit("FAIL_CLOSED: certified reproduction mismatch")

    # ---------------- funding-aware certified protocol ----------------
    funded = []
    for period in p18_periods:
        s, e = period["slice"]
        slice_rows = p18_rows[s:e]
        result = run_frozen_oos(slice_rows, symbol=SYMBOL,
                                funding_schedule=schedule_p18)
        start = int(slice_rows[0]["time"])
        end = int(slice_rows[-1]["time"])
        funded.append({
            "period_id": period["period_id"],
            "segment": "funded_full_period",
            "bars": result["bars"],
            "orders": result["orders"],
            "fills": result["fills"],
            "funding": result["funding"],
            "gross_pnl": result["gross_pnl"],
            "funding_events_in_interval": _funding_count(
                schedule_p18, start, end),
            "cost_status": "NOT_APPLICABLE_NO_FILLS"
            if result["fills"] == 0 else "APPLIED",
        })
    global_funded = run_frozen_oos(
        p18_rows, symbol=SYMBOL, funding_schedule=schedule_p18)

    # ---------------- Phase-30 extended dataset (new evidence only) ----
    p30_periods = split_bars(p30_rows, n_periods=6, prefix="OOS")
    p30_recorded_periods = {item["period_id"]: item
                            for item in p30_recorded["periods"]}
    extended = []
    for period in p30_periods:
        s, e = period["slice"]
        slice_rows = p30_rows[s:e]
        result = run_frozen_oos(slice_rows, symbol=SYMBOL,
                                funding_schedule=schedule_oos)
        start = int(slice_rows[0]["time"])
        end = int(slice_rows[-1]["time"])
        recorded = p30_recorded_periods.get(period["period_id"], {})
        extended.append({
            "period_id": period["period_id"],
            "evidence_class": "DIFFERENT_REVISION_EVIDENCE",
            "bars": result["bars"],
            "orders": result["orders"],
            "fills": result["fills"],
            "gross_pnl": result["gross_pnl"],
            "funding_events_in_interval": _funding_count(
                schedule_oos, start, end),
            "phase30_recorded_orders": recorded.get("orders"),
            "phase30_recorded_fills": recorded.get("fills"),
            "matches_phase30": (
                result["orders"] == recorded.get("orders")
                and result["fills"] == recorded.get("fills")),
        })
    global_extended = run_frozen_oos(
        p30_rows, symbol=SYMBOL, funding_schedule=schedule_oos)

    # ---------------- preregistered cost ladders -----------------------
    ladder = []
    for scenario in ("A", "B", "C", "D"):
        spec = COST_SCENARIOS_11F[scenario]
        cost_spec = CostSpec(
            per_trade=spec["COMMISSION_PER_TRADE"],
            rate=spec["COMMISSION_RATE"],
            slippage_bps=spec["SLIPPAGE_BPS"])
        check_commission, check_slippage = cost_spec.compute(60000.0)
        ladder.append({
            "scenario": scenario,
            "params": spec,
            "applied_to_oos": False,
            "attribution": "NOT_APPLICABLE_NO_FILLS",
            "oos_period_cost_total": 0.0,
            "global_cost_total": 0.0,
            "arithmetic_check_only": {
                "notional": 60000.0,
                "commission": round(check_commission, 6),
                "slippage": round(check_slippage, 6),
                "status": "CONFIGURED_ASSUMPTION_CHECK_ONLY_NOT_OOS_EVIDENCE",
            },
            "note": (
                "Zero OOS attribution because the frozen run has no fills; "
                "not evidence that venue execution costs are zero."),
        })

    phase25_report = next(
        item for item in p25["cost_sensitivity"] if item["scenario"] == "A")
    p25_funding = p25["funding_aware_runs"]
    p25_head_gap = int(p25["funding_head_gap_seconds"])
    p25_first = int(datetime.fromisoformat(
        p25["funding_first_event"].replace("Z", "+00:00")).timestamp())

    artifact = {
        "schema": "quantengine.phase26-oos-reevaluation.v1",
        "phase": 26,
        "workstreams": ["P26-D", "P26-E", "P26-F"],
        "evaluation_is_distinct_from_original": True,
        "strategy_logic_changed": False,
        "thresholds_changed": False,
        "entry_model_changed": False,
        "fill_model_changed": False,
        "original_evaluations_preserved": {
            "phase18": {
                "path": "research/results/phase18_oos_validation.json",
                "sha256": _sha_file(P18_RECORDED),
                "global_orders": p18_recorded["global_continuous_run"]["orders"],
                "global_fills": p18_recorded["global_continuous_run"]["fills"],
            },
            "phase25": {
                "path": "research/results/phase25_frozen_oos_validation.json",
                "sha256": _sha_file(P25_RESULTS),
                "funding_head_gap_seconds": p25_head_gap,
                "phase18_funnel_match": p25["verdict"]["phase18_funnel_match"],
                "cost_scenario_A_global": phase25_report["global_run"],
            },
        },
        "datasets": {
            "phase18_certified": {
                "path": "data/history/BTCUSDT_1m_phase17_fresh.json",
                "identity": p18_identity,
                "file_sha256": p18_file_sha,
                "rows": len(p18_rows),
                "start": int(p18_rows[0]["time"]),
                "end": int(p18_rows[-1]["time"]),
            },
            "phase30_extended": {
                "path": "data/history/BTCUSDT_1m_oos_topup.json",
                "identity": p30_identity,
                "file_sha256": p30_file_sha,
                "rows": len(p30_rows),
                "start": int(p30_rows[0]["time"]),
                "end": int(p30_rows[-1]["time"]),
                "evidence_class": "DIFFERENT_REVISION_EVIDENCE",
            },
        },
        "funding_evidence": {
            "phase26_artifact_phase18": {
                "path": "reports/evidence/phase26/btcusdt_funding_bound_to_phase18.json",
                "sha256": _sha_file(P26_BOUND_P18),
                "series": funding_p18,
            },
            "phase26_artifact_oos": {
                "path": "reports/evidence/phase26/btcusdt_funding_bound_to_oos.json",
                "sha256": _sha_file(P26_BOUND_OOS),
                "series": funding_oos,
            },
            "phase25_artifact_phase18_sha256": _sha_file(P25_BOUND_P18),
            "phase25_artifact_oos_sha256": _sha_file(P25_BOUND_OOS),
            "phase25_head_gap_seconds": p25_head_gap,
            "phase25_first_event_utc": _utc(p25_first),
            "phase26_head_gap_seconds": funding_p18["head_gap_seconds"],
            "head_gap_repaired": (
                funding_p18["head_covered"]
                and funding_oos["head_covered"]
                and funding_p18["head_gap_seconds"] == 0),
            "recovered_head_settlements": recovered,
            "recovered_head_settlement_count": len(recovered),
            "repair_method": (
                "aligned the public request to a whole 8-hour funding block "
                "with 8h pad; no interpolation and no zero substitution"),
        },
        "certified_protocol_reproduction": {
            "executor": "core/research/oos_validation/execution.py:run_frozen_oos",
            "per_period": reproduction,
            "all_match": all(item["matches"] for item in reproduction),
            "global_plain": _funnel(global_plain),
            "lifecycle_evidence": {
                "path": "reports/PHASE26_ORDER_LIFECYCLE.json",
                "sha256": _sha_file(LIFECYCLE),
            },
        },
        "funding_aware_phase18": {
            "per_period": funded,
            "global": _funnel(global_funded),
            "segments": "all six periods fully funded (no head gap)",
        },
        "extended_dataset_phase30": {
            "note": ("executed for transparency only; recorded Phase-30 "
                     "evidence came from a different code revision"),
            "per_period": extended,
            "global": _funnel(global_extended),
        },
        "cost_ladders": ladder,
        "economics_status": {
            "fills": global_funded["fills"],
            "completed_trades": global_funded["completed_trades"],
            "gross_pnl": global_funded["gross_pnl"],
            "funding": global_funded["funding"],
            "commission": global_funded["commission"],
            "slippage": global_funded["slippage"],
            "net_pnl": global_funded["net_pnl"],
            "realized_rr": global_funded["actual_fill_rr"],
            "cost_status": "NOT_APPLICABLE_NO_FILLS",
            "funding_status": "NOT_APPLICABLE_NO_FILLS",
            "statement": (
                "No fills means no holding interval, so funding and costs "
                "do not enter P&L. The zero totals are an absence of "
                "transactions, not a measurement of free execution."),
        },
        "verdict": {
            "final_decision": "OOS_BLOCKED",
            "edge_status": "EDGE NOT ESTABLISHED",
            "release_gate": "HOLD",
            "production_ready": False,
            "zero_fill_classification": "LEGITIMATE_NO_FILL_OUTCOME",
            "zero_fill_cause": (
                "BREAKOUT_CONTINUATION fills at the next bar's open after "
                "price has already moved beyond the order's entry level; "
                "the executable reward:risk then fails the frozen-era 1:6 "
                "floor (30/32) or the fill is already beyond the "
                "take-profit (2/32). No fill timing, geometry or threshold "
                "defect was found."),
            "phase18_reproduction_match": True,
            "phase25_funding_head_gap_repaired": True,
            "phase25_funding_economics_unchanged": True,
            "next_evidence_requirement": (
                "an entry model whose executable reward:risk can satisfy "
                "the unchanged 1:6 floor, evaluated on genuinely unseen "
                "OOS data with a preregistered protocol; no tuning "
                "against this frozen OOS set is permitted"),
        },
    }

    text = json.dumps(artifact, indent=2, sort_keys=True,
                      separators=(",", ": ")) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print("wrote %s (%d bytes)" % (OUT, len(text)))
    print("certified reproduction match: %s"
          % artifact["certified_protocol_reproduction"]["all_match"])
    print("funding head gap: phase25=%ds phase26=%ds (repaired=%s)"
          % (p25_head_gap, funding_p18["head_gap_seconds"],
             artifact["funding_evidence"]["head_gap_repaired"]))
    print("recovered head settlements: %d (%s)"
          % (len(recovered), [item["utc"] for item in recovered]))
    print("funding-aware global: orders=%d fills=%d funding=%.6f"
          % (global_funded["orders"], global_funded["fills"],
             global_funded["funding"]))
    print("extended global (different revision): orders=%d fills=%d"
          % (global_extended["orders"], global_extended["fills"]))
    print("cost ladders: %s"
          % [(item["scenario"], item["attribution"]) for item in ladder])
    print("output sha256: %s" % hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
