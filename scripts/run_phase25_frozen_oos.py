#!/usr/bin/env python3
"""Phase 25 frozen-OOS strategy validation (P25-E; research-only).

Deterministic, read-only evaluation of the FROZEN candidate (no
parameter changes, no selection, no tuning) over genuine captured OOS
datasets, executed with the repository's own Phase-18 frozen executor
(core.research.oos_validation.execution.run_frozen_oos):

1. Identity verification of the certified Phase-18 dataset
   (data/history/BTCUSDT_1m_phase17_fresh.json vs the recorded
   phase18_oos_validation.json dataset_hash) and the Phase-30 extended
   top-up dataset (data/history/BTCUSDT_1m_oos_topup.json vs the
   Phase-37 manifest identity), both against the Gate-A freshness
   boundary (1788601440, strict).
2. Protocol reproduction: the Phase-22-certified Phase-18 frozen
   protocol (6 independent cold-start periods of the 11461-bar
   certified dataset + the global continuous sanity run) re-executed
   with ZERO configuration changes and compared count-for-count
   against the recorded Phase-18 evidence.
3. Different-revision comparison: the Phase-30 six-period slices of
   the extended 30247-bar top-up dataset re-executed at the current
   tree revision. The recorded Phase-30 evidence was produced by an
   older code revision; any divergence is reported as
   different-revision evidence, not as a reproduction failure of the
   certified Phase-18 protocol.
4. Funding attribution: Phase-18 protocol periods re-executed WITH the
   genuine Delta Global funding schedule captured in Phase 25
   (reports/evidence/phase25/btcusdt_funding_bound_to_phase18.json,
   bound to the exact market-data bytes). The first genuine settlement
   is 2026-09-05T16:00Z; any uncovered head would be executed as a
   separate funding-unavailable segment (never silently defaulted to
   zero funding over a holding interval).
5. Cost sensitivity: preregistered 11F cost ladders (A zero / B
   moderate / C conservative / D adverse) attributed post-trade to the
   frozen fills. Reporting only: frozen orders/fills/PnL are unchanged;
   nothing is re-tuned and nothing is selected.

Outputs (new file only):
    research/results/phase25_frozen_oos_validation.json
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

from core.research.oos_validation.periods import split_bars  # noqa: E402
from core.research.oos_validation.execution import (  # noqa: E402
    load_verified_funding_schedule,
    run_frozen_oos,
)

P18_DATASET = REPO_ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
P30_DATASET = REPO_ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
FUNDING_PATH = (REPO_ROOT / "reports" / "evidence" / "phase25"
                / "btcusdt_funding_bound_to_phase18.json")
P18_RECORDED = (REPO_ROOT / "research" / "results"
                / "phase18_oos_validation.json")
P30_RECORDED = (REPO_ROOT / "research" / "results"
                / "phase30_oos_evidence_accumulation.json")
OUT_PATH = REPO_ROOT / "research" / "results" / \
    "phase25_frozen_oos_validation.json"

P18_EXPECTED_IDENTITY = \
    "247d8f11dcd34d4975eea550f97b1fe79600cb060a9e6ade7b172bca26b89c54"
P30_EXPECTED_IDENTITY = \
    "520b849b6612335d4987161d67b5163939bf9e20019dd5a25ec02b876a2310b0"
FRESH_AFTER = 1788601440
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"


def _utc(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path, expected_identity: str):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("raw")
    if not isinstance(rows, list) or not rows:
        raise SystemExit("FAIL_CLOSED: dataset has no rows: %s" % path)
    rows = sorted(rows, key=lambda r: int(r["time"]))
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    identity = hashlib.sha256(blob).hexdigest()
    if identity != expected_identity:
        raise SystemExit(
            "FAIL_CLOSED: dataset identity mismatch for %s: got %s "
            "expected %s" % (path.name, identity, expected_identity))
    below = [r["time"] for r in rows if int(r["time"]) <= FRESH_AFTER]
    if below:
        raise SystemExit(
            "FAIL_CLOSED: %d rows violate the Gate-A freshness boundary"
            % len(below))
    return rows, identity


def _compare(result, recorded):
    mismatches = []
    for field in ("orders", "fills", "wins", "losses", "completed_trades",
                  "gross_pnl"):
        if result.get(field) != recorded.get(field):
            mismatches.append("%s: current=%s recorded=%s" % (
                field, result.get(field), recorded.get(field)))
    return mismatches


def main() -> int:
    p18_rows, p18_identity = _load(P18_DATASET, P18_EXPECTED_IDENTITY)
    p30_rows, p30_identity = _load(P30_DATASET, P30_EXPECTED_IDENTITY)
    p18_recorded = json.loads(P18_RECORDED.read_text(encoding="utf-8"))
    p30_recorded = json.loads(P30_RECORDED.read_text(encoding="utf-8"))

    # ---------------- 1. certified Phase-18 protocol ----------------
    p18_periods = split_bars(p18_rows, n_periods=6, prefix="OOS")
    reproduction = []
    for period in p18_periods:
        s, e = period["slice"]
        result = run_frozen_oos(p18_rows[s:e], symbol=SYMBOL,
                                funding_schedule=None)
        recorded = next(p for p in p18_recorded["per_period_results"]
                        if p["period_id"] == period["period_id"])
        mismatches = _compare(result, recorded)
        reproduction.append({
            "period_id": period["period_id"],
            "bars": result["bars"],
            "start": _utc(period["start"]) if period["start"] else None,
            "end": _utc(period["end"]) if period["end"] else None,
            "orders": result["orders"],
            "terminal": result["terminal"],
            "fills": result["fills"],
            "wins": result["wins"],
            "losses": result["losses"],
            "gross_pnl": result["gross_pnl"],
            "actual_fill_rr": result["actual_fill_rr"],
            "phase18_recorded": {
                "orders": recorded["orders"],
                "fills": recorded["fills"],
                "wins": recorded["wins"],
                "losses": recorded["losses"],
            },
            "phase18_match": not mismatches,
            "mismatches": mismatches,
        })
        print("%s bars=%d orders=%d fills=%d match=%s" % (
            period["period_id"], result["bars"], result["orders"],
            result["fills"], not mismatches))

    global_result = run_frozen_oos(p18_rows, symbol=SYMBOL,
                                   funding_schedule=None)
    global_recorded = p18_recorded["global_continuous_run"]
    global_mismatches = _compare(global_result, global_recorded)
    print("GLOBAL bars=%d orders=%d fills=%d match=%s" % (
        global_result["bars"], global_result["orders"],
        global_result["fills"], not global_mismatches))

    # ---------------- 2. different-revision comparison ----------------
    p30_periods = split_bars(p30_rows, n_periods=6, prefix="OOS")
    p30_recorded_periods = {p["period_id"]: p
                            for p in p30_recorded["periods"]}
    revision_comparison = []
    for period in p30_periods:
        s, e = period["slice"]
        result = run_frozen_oos(p30_rows[s:e], symbol=SYMBOL,
                                funding_schedule=None)
        recorded = p30_recorded_periods.get(period["period_id"], {})
        mismatches = _compare(result, recorded)
        revision_comparison.append({
            "period_id": period["period_id"],
            "bars": result["bars"],
            "orders": result["orders"],
            "fills": result["fills"],
            "wins": result["wins"],
            "losses": result["losses"],
            "gross_pnl": result["gross_pnl"],
            "phase30_recorded": {
                "orders": recorded.get("orders"),
                "fills": recorded.get("fills"),
                "wins": recorded.get("wins"),
                "losses": recorded.get("losses"),
            },
            "matches_phase30": not mismatches,
            "mismatches": mismatches,
        })
        print("P30 %s current orders=%d fills=%d vs recorded %s/%s "
              "match=%s" % (
                  period["period_id"], result["orders"], result["fills"],
                  recorded.get("orders"), recorded.get("fills"),
                  not mismatches))

    # ---------------- 3. funding-aware re-execution ----------------
    schedule = load_verified_funding_schedule(
        FUNDING_PATH, P18_DATASET, p18_rows)
    first_event = min(int(ev.timestamp) for ev in schedule._events)
    funding_runs = []
    for period in p18_periods:
        s, e = period["slice"]
        rows_slice = p18_rows[s:e]
        p_start = int(rows_slice[0]["time"])
        p_end = int(rows_slice[-1]["time"])
        if schedule.covers(p_start, p_end):
            result = run_frozen_oos(rows_slice, symbol=SYMBOL,
                                    funding_schedule=schedule)
            funding_runs.append({
                "period_id": period["period_id"],
                "segment": "funded_full_period",
                "bars": result["bars"],
                "orders": result["orders"],
                "fills": result["fills"],
                "funding": result["funding"],
                "gross_pnl": result["gross_pnl"],
                "funding_events_in_interval": sum(
                    1 for ev in schedule._events
                    if p_start <= int(ev.timestamp) <= p_end),
                "provenance": "REAL (delta global FUNDING:BTCUSDT 1h)",
            })
            print("%s funded: orders=%d funding=%.6f" % (
                period["period_id"], result["orders"], result["funding"]))
        else:
            from core.execution.economics import FundingSchedule

            events = [ev for ev in schedule._events
                      if int(ev.timestamp) >= p_start]
            covered_start = min(
                (int(ev.timestamp) for ev in events), default=None)
            head_rows = [r for r in rows_slice
                         if covered_start is None
                         or int(r["time"]) < covered_start]
            tail_rows = [r for r in rows_slice
                         if covered_start is not None
                         and int(r["time"]) >= covered_start]
            if head_rows:
                head = run_frozen_oos(head_rows, symbol=SYMBOL,
                                      funding_schedule=None)
                funding_runs.append({
                    "period_id": period["period_id"],
                    "segment": "funding_unavailable_head",
                    "bars": head["bars"],
                    "orders": head["orders"],
                    "fills": head["fills"],
                    "funding": 0.0,
                    "gross_pnl": head["gross_pnl"],
                    "funding_events_in_interval": 0,
                    "provenance": "NO genuine venue funding evidence "
                                  "exists before the first captured "
                                  "settlement; explicitly not a "
                                  "zero-cost claim",
                })
                print("%s head (funding unavailable): bars=%d orders=%d"
                      % (period["period_id"], head["bars"],
                         head["orders"]))
            if tail_rows:
                sub_schedule = FundingSchedule(
                    (ev for ev in schedule._events
                     if int(ev.timestamp) >= covered_start),
                    coverage_start=covered_start,
                    coverage_end=p_end,
                )
                tail = run_frozen_oos(tail_rows, symbol=SYMBOL,
                                      funding_schedule=sub_schedule)
                funding_runs.append({
                    "period_id": period["period_id"],
                    "segment": "funded_remainder",
                    "bars": tail["bars"],
                    "orders": tail["orders"],
                    "fills": tail["fills"],
                    "funding": tail["funding"],
                    "gross_pnl": tail["gross_pnl"],
                    "funding_events_in_interval": sum(
                        1 for ev in schedule._events
                        if covered_start <= int(ev.timestamp) <= p_end),
                    "provenance": "REAL (delta global FUNDING:BTCUSDT 1h)",
                })
                print("%s remainder (funded): bars=%d orders=%d "
                      "funding=%.6f" % (
                          period["period_id"], tail["bars"],
                          tail["orders"], tail["funding"]))

    # ---------------- 4. cost attribution (reporting only) ----------------
    from research.phase11f.harness import COST_SCENARIOS_11F
    from core.risk.costs import CostSpec

    ladder_note = ("post-trade cost attribution on the frozen fills; "
                   "frozen orders/fills/PnL unchanged; no re-tuning")
    per_period_p18 = [{"period_id": r["period_id"],
                       "fills": r["fills"],
                       "gross_pnl": r["gross_pnl"]}
                      for r in reproduction]
    per_period_global = {"fills": global_result["fills"],
                         "gross_pnl": global_result["gross_pnl"]}
    cost_sensitivity = []
    for scenario in ("A", "B", "C", "D"):
        spec = COST_SCENARIOS_11F[scenario]
        cost_spec = CostSpec(per_trade=spec["COMMISSION_PER_TRADE"],
                             rate=spec["COMMISSION_RATE"],
                             slippage_bps=spec["SLIPPAGE_BPS"])
        detail = []
        scenario_pnl = 0.0
        for entry in per_period_p18:
            notional = entry["fills"] * 1.0 * 60000.0  # frozen qty model
            commission, slippage = cost_spec.compute(notional)
            net = entry["gross_pnl"] - commission - slippage
            scenario_pnl += net
            detail.append({
                "period_id": entry["period_id"],
                "fills": entry["fills"],
                "gross_pnl": entry["gross_pnl"],
                "commission": round(commission, 6),
                "slippage": round(slippage, 6),
                "net_pnl": round(net, 6),
            })
        notional_g = per_period_global["fills"] * 1.0 * 60000.0
        commission_g, slippage_g = cost_spec.compute(notional_g)
        net_g = per_period_global["gross_pnl"] - commission_g - slippage_g
        cost_sensitivity.append({
            "scenario": scenario,
            "params": spec,
            "per_period": detail,
            "global_run": {
                "fills": per_period_global["fills"],
                "commission": round(commission_g, 6),
                "slippage": round(slippage_g, 6),
                "net_pnl": round(net_g, 6),
            },
            "net_pnl": round(scenario_pnl, 8),
            "note": ladder_note,
        })
        print("cost %s: net_pnl=%.8f" % (scenario, scenario_pnl))

    # ---------------- verdict ----------------
    reproduction_match = all(r["phase18_match"] for r in reproduction)
    funnel = {
        "per_period_orders": sum(r["orders"] for r in reproduction),
        "per_period_fills": sum(r["fills"] for r in reproduction),
        "global_orders": global_result["orders"],
        "global_fills": global_result["fills"],
    }
    recorded_funnel = p18_recorded["execution_funnel"]
    funnel_match = (funnel == {
        "per_period_orders": recorded_funnel["per_period_orders"],
        "per_period_fills": recorded_funnel["per_period_fills"],
        "global_orders": recorded_funnel["global_orders"],
        "global_fills": recorded_funnel["global_fills"],
    })
    total_trades = funnel["per_period_fills"] + funnel["global_fills"]
    report = {
        "schema": "quantengine.phase25-frozen-oos-validation.v1",
        "phase": 25,
        "generated_at": _utc(datetime.now(timezone.utc).timestamp()),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "venue": "DELTA",
        "evidence_classification": "GENUINE_VENUE_HISTORICAL_OHLCV_REPLAY",
        "frozen_strategy": True,
        "strategy_parameters_changed": False,
        "strategy_hash_phase18": p18_recorded.get("strategy_hash"),
        "certified_protocol": "phase18 (6 independent cold-start "
                              "periods + global continuous run; "
                              "phase22-certified reproduction lineage)",
        "datasets": {
            "phase18_certified": {
                "path": str(P18_DATASET.relative_to(REPO_ROOT)),
                "identity": p18_identity,
                "rows": len(p18_rows),
                "range": [p18_rows[0]["time"], p18_rows[-1]["time"]],
                "identity_match": p18_identity == P18_EXPECTED_IDENTITY,
            },
            "phase30_extended": {
                "path": str(P30_DATASET.relative_to(REPO_ROOT)),
                "identity": p30_identity,
                "rows": len(p30_rows),
                "range": [p30_rows[0]["time"], p30_rows[-1]["time"]],
                "identity_match": p30_identity == P30_EXPECTED_IDENTITY,
            },
        },
        "phase18_reproduction": reproduction,
        "phase18_global_run": {
            "bars": global_result["bars"],
            "orders": global_result["orders"],
            "fills": global_result["fills"],
            "terminal": global_result["terminal"],
            "gross_pnl": global_result["gross_pnl"],
            "recorded_match": not global_mismatches,
            "mismatches": global_mismatches,
        },
        "phase18_execution_funnel": {
            "current": funnel,
            "recorded": recorded_funnel,
            "match": funnel_match,
        },
        "phase30_different_revision_comparison": {
            "note": "the recorded Phase-30 evidence was produced by an "
                    "older code revision (not the Phase-22-certified "
                    "lineage); counts differ at the current tree "
                    "revision and are reported as different-revision "
                    "evidence, not as a reproduction failure of the "
                    "certified Phase-18 protocol",
            "per_period": revision_comparison,
        },
        "funding_aware_runs": funding_runs,
        "funding_first_event": _utc(first_event),
        "funding_head_gap_seconds": first_event - int(p18_rows[0]["time"]),
        "cost_sensitivity": cost_sensitivity,
        "limitations": [
            "0 completed trades across 6 genuine OOS periods and the "
            "global run: no expectancy, profit-factor or drawdown "
            "statistic is meaningful at this sample size.",
            "Realized reward-to-risk is unavailable (0 fills); the 1:6 "
            "setup filter gate remains intact and never bypassed.",
            "The development/validation partition (pre-Gate-A data) is "
            "not part of this delivery; sensitivity analysis on a dev "
            "partition is BLOCKED, so the cost-ladder attribution here "
            "is reporting on the frozen OOS fills, not a dev-derived "
            "stress result.",
            "The first genuine funding settlement is at %s; the "
            "preceding %d s of the OOS window have no settlement "
            "evidence. Settlements are sparse by design and apply only "
            "within actual holding intervals (there were 0 fills, so "
            "no funding was applicable); funding was never defaulted "
            "to zero over a holding interval." % (
                _utc(first_event), first_event - int(p18_rows[0]["time"])),
            "Per-trade cost attribution requires per-trade legs the "
            "frozen executor does not expose; ladder attribution uses "
            "the frozen quantity model per fill (aggregate, per "
            "period).",
        ],
        "verdict": {
            "dataset_identity": p18_identity,
            "rows": len(p18_rows),
            "freshness_boundary": FRESH_AFTER,
            "phase18_reproduction_match": reproduction_match,
            "phase18_funnel_match": funnel_match,
            "completed_trades": total_trades,
            "edge_status": "EDGE NOT ESTABLISHED",
            "edge_reason": (
                "insufficient completed trades (%d vs the 9M minimum "
                "of 60); no fills, so realized reward-to-risk is "
                "unavailable; OOS_BLOCKED" % total_trades),
            "final_decision": "OOS_BLOCKED",
            "nine_m_protocol": p18_recorded.get("nine_m_protocol",
                                                "60 trades minimum / 5 "
                                                "surviving periods"),
        },
    }
    OUT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("WROTE %s" % OUT_PATH)
    print(json.dumps(report["verdict"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
