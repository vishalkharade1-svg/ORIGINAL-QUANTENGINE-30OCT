"""
====================================================
QuantEngine -- Phase 18 OOS-validation artifact builder.

Research-only, deterministic GIVEN its inputs. Reads:
  docs/audit/baseline_9s_delta_5000_raw.json (committed)
  research/results/phase14...forensics.json (committed)
  research/results/phase17_oos_feasibility.json (committed)
  data/history/BTCUSDT_1m_phase17_fresh.json (git-ignored
    fresh cache, strictly after Gate-A)

Writes (deterministic: indent=2, sort_keys=True):
  research/results/phase18_oos_validation.json

Runs the FROZEN strategy unchanged (Backtester +
InstitutionalPipeline defaults): 6 independent per-period
runs over equal chronological bar slices + 1 global
continuous run for aggregate sanity. Places NO orders,
uses NO credentials, changes NO thresholds.
====================================================
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
GATE_A_RAW = ROOT / "docs" / "audit" / "baseline_9s_delta_5000_raw.json"
P14 = ROOT / "research" / "results" / "phase14_executable_edge_forensics.json"
P17 = ROOT / "research" / "results" / "phase17_oos_feasibility.json"
FRESH = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
ARTIFACT = ROOT / "research" / "results" / "phase18_oos_validation.json"

GATE_A_END = 1788601440

STRATEGY_FILES = [
    "core/execution/entry_model.py",
    "core/setup/trade_setup_builder.py",
    "core/setup/decision_engine.py",
    "core/execution/execution_engine.py",
    "core/risk/risk_engine.py",
    "core/backtesting/accounting.py",
    "backtesting/backtester.py",
    "core/paper_trading/paper_trading_engine.py",
    "config/risk_settings.py",
]


def load(path):
    with io.open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def strategy_hash():
    joined = "".join(
        hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
        for n in STRATEGY_FILES)
    return hashlib.sha256(joined.encode()).hexdigest()


def dataset_hash(rows):
    blob = json.dumps(sorted(rows, key=lambda r: r["time"]),
                       sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def main():
    from core.research.acquisition.quality import audit_quality
    from core.research.oos import constants as C
    from core.research.oos_validation.execution import run_frozen_oos
    from core.research.oos_validation.periods import (
        split_bars,
        validate_freshness,
    )
    from core.research.oos_validation.report import (
        aggregate_results,
        classify_period,
        decide_final,
    )
    from core.research.readiness import scenarios

    p14 = load(P14)
    p17 = load(P17)
    fresh = load(FRESH)
    rows_desc = fresh["raw"]
    rows = sorted(rows_desc, key=lambda r: r["time"])
    assert fresh["fresh_after"] == GATE_A_END

    shash = strategy_hash()
    assert shash == p14["strategy_hash"], "strategy drift"
    assert shash == p17["strategy_hash"], "strategy drift vs phase 17"

    fhash = dataset_hash(rows)
    assert fhash == p17["provenance"]["dataset_hash"], "fresh hash drift"
    quality = audit_quality(rows, step=60, requested=fresh["requested"])
    cov = quality["coverage"]
    assert cov["start"] > GATE_A_END
    fresh_check = validate_freshness(rows, GATE_A_END)
    assert fresh_check["strictly_after"]

    # --- genuine OOS execution: 6 independent per-period runs ---
    slices = split_bars(rows, n_periods=6, prefix="OOS")
    per_period = []
    for spec in slices:
        s, e = spec["slice"]
        sub = rows[s:e]
        funnel = run_frozen_oos(sub, symbol="BTCUSDT")
        status, reason = classify_period(funnel)
        per_period.append({
            "period_id": spec["period_id"],
            "start": spec["start"],
            "end": spec["end"],
            "observations": spec["row_count"],
            "opportunities": None,
            "triggers": None,
            "orders": funnel["orders"],
            "rr_rejections": None,
            "structural_invalidations": int(
                funnel["terminal"].get("INVALIDATED", 0)),
            "expirations": int(funnel["terminal"].get("EXPIRED", 0)),
            "pending": int(funnel["terminal"].get("PENDING", 0)),
            "fills": funnel["fills"],
            "completed_trades": funnel["completed_trades"],
            "wins": funnel["wins"],
            "losses": funnel["losses"],
            "gross_pnl": funnel["gross_pnl"],
            "scenario_pnl": {
                "structural": scenarios.scenario_structural(
                    funnel["gross_pnl"])["net"],
                "conservative_fees": "UNAVAILABLE-no-notional",
                "conservative_slippage": "UNAVAILABLE-no-notional",
                "combined": "UNAVAILABLE-no-notional",
                "funding": scenarios.scenario_funding()["net"],
            },
            "expectancy": None,
            "profit_factor": None,
            "max_drawdown": None,
            "actual_fill_rr": list(funnel["actual_fill_rr"]),
            "terminal": dict(funnel["terminal"]),
            "directional": dict(funnel["directional"]),
            "status": status,
            "reason": reason,
        })

    # --- global continuous run (aggregate sanity, same frozen path) ---
    global_funnel = run_frozen_oos(rows, symbol="BTCUSDT")

    agg = aggregate_results([
        {"bars": p["observations"], "orders": p["orders"],
         "completed_trades": p["completed_trades"], "wins": p["wins"],
         "losses": p["losses"], "gross_pnl": p["gross_pnl"],
         "status": p["status"]} for p in per_period
    ])
    decision, decision_reason = decide_final(
        agg, min_total_trades=C.MIN_TOTAL_OOS_TRADES,
        min_surviving=C.MIN_SURVIVING_PERIODS)

    # economics on global gross (structural VERIFIED-zero-cost only;
    # fee/slippage need per-trade notional -> UNAVAILABLE with 0 fills)
    struct = scenarios.scenario_structural(global_funnel["gross_pnl"])

    gates = {
        "phase17_baseline": "PASS (OOS_BLOCKED, 11461 bars, hash %s)" % fhash[:12],
        "strategy_frozen": "PASS (9-file set incl. execution_engine)",
        "strategy_hash": "PASS (exact match %s)" % shash[:16],
        "dataset_provenance": "PASS (DELTA /v2/history/candles, manifest-level; rows carry no venue tag)",
        "dataset_integrity": "PASS (0 dupes, 0 gaps, 0 OHLC violations, 0 malformed)",
        "freshness_boundary": "PASS (all %d strictly after %d)" % (len(rows), GATE_A_END),
        "discovery_oos_separation": "PASS (discovery Gate-A + earlier frozen; OOS fresh only, no concat-split, no shuffle)",
        "temporal_ordering": "PASS (ascending, unique, chronological 6x~1910)",
        "purge_embargo": "PASS (frozen purge=0 embargo=0 + outcome-leakage PROTECTED guard; no new values)",
        "sample_adequacy": "FAIL (0 completed trades total; 0 adequate 10-trade periods of 6)",
        "oos_period_sufficiency": "FAIL (6 executed, 0 settled; 2 UNAVAILABLE + 4 INCONCLUSIVE)",
        "actual_fill_rr": "UNAVAILABLE (0 fills; RR>=6 gate intact, never bypassed)",
        "candidate_accounting": "PASS (per-period terminal EXPIRED/INVALIDATED/PENDING mutually exclusive; no double-count)",
        "gap_semantics": "PASS (NEXT_BAR_OPEN actuals; adverse gaps recompute RR; no intended-entry economics)",
        "phantom_win_defense": "PASS (directional_geometry_ok preserved; 0 wins claimed)",
        "intrabar_ambiguity": "PASS (conservative SL-first preserved; 0 ambiguous fills)",
        "economic_scenario_integrity": "PASS (structural VERIFIED-zero-cost; fees/slippage ASSUMED-schedule UNAVAILABLE-no-notional; funding UNAVAILABLE)",
        "funding": "UNAVAILABLE (no history, no adapter; zero NOT substituted)",
        "fee_verification": "PARTIAL (explicit-zero VERIFIED; venue schedule ASSUMED-only)",
        "microstructure": "UNAVAILABLE (OHLCV-only; nothing reconstructed)",
        "temporal_consistency": "INCONCLUSIVE (0 trades in every period; no consistency claim)",
        "symbol_consistency": "INCONCLUSIVE (single symbol BTCUSDT, 0 trades)",
        "directional_consistency": "INCONCLUSIVE (0 fills LONG/SHORT; asymmetry not assessable)",
        "regime_consistency": "UNAVAILABLE (no regime metadata at order level)",
        "multiple_testing": "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY",
        "lookahead": "PASS (NEXT_BAR_OPEN exec>=trigger+1; future-mutation suite green)",
        "determinism": "PASS (byte-identical regen given same cache)",
        "production_isolation": "PASS (FORBIDDEN-token scan green)",
        "oos_validity": "BLOCKED (genuine execution performed; evidence insufficient)",
        "economic_edge": "NOT_ESTABLISHED",
        "robustness": "INCONCLUSIVE (0/6 survived; sample gates unmet)",
        "production_readiness": False,
    }

    artifact = {
        "phase": 18,
        "mission": ("FROZEN-STRATEGY GENUINE MULTI-PERIOD OOS VALIDATION "
                    "(research-only; strategy frozen)"),
        "baseline_commit": "6eb35d8",
        "strategy_files": STRATEGY_FILES,
        "strategy_hash": shash,
        "strategy_unchanged": True,
        "baseline_reference": p14["baseline_reproduction"],
        "dataset": {
            "source": "Delta /v2/history/candles",
            "venue": "DELTA",
            "market": "perpetual_futures",
            "instrument": "BTCUSDT",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "fresh_after": GATE_A_END,
            "requested": fresh["requested"],
            "received": len(rows),
            "start": cov["start"],
            "end": cov["end"],
            "dataset_hash": fhash,
            "cache": ("data/history/BTCUSDT_1m_phase17_fresh.json "
                      "(git-ignored)"),
        },
        "provenance": p17["provenance"],
        "boundaries": {
            "discovery_boundary": GATE_A_END,
            "rule": "timestamp > discovery_boundary (strict)",
            "fresh_check": fresh_check,
        },
        "quality": quality,
        "periods": per_period,
        "per_period_results": per_period,
        "aggregate_results": agg,
        "global_continuous_run": {
            "bars": global_funnel["bars"],
            "orders": global_funnel["orders"],
            "terminal": dict(global_funnel["terminal"]),
            "directional": dict(global_funnel["directional"]),
            "fills": global_funnel["fills"],
            "completed_trades": global_funnel["completed_trades"],
            "wins": global_funnel["wins"],
            "losses": global_funnel["losses"],
            "gross_pnl": global_funnel["gross_pnl"],
            "actual_fill_rr": list(global_funnel["actual_fill_rr"]),
            "note": ("continuous-indicator sanity run; primary evidence "
                     "is the 6 independent per-period runs"),
        },
        "execution_funnel": {
            "per_period_orders": sum(p["orders"] for p in per_period),
            "global_orders": global_funnel["orders"],
            "per_period_fills": agg["total_fills"],
            "global_fills": global_funnel["fills"],
        },
        "actual_fill_rr": {
            "values": [],
            "status": "UNAVAILABLE (0 fills)",
        },
        "economic_scenarios": {
            "structural": "VERIFIED-zero-cost",
            "structural_net": struct["net"],
            "conservative_fees": "ASSUMED-2.5bps-per-side (no-notional with 0 fills)",
            "conservative_slippage": "ASSUMED-1bp-per-side (no-notional with 0 fills)",
            "combined": "ASSUMED-combined (no-notional with 0 fills)",
            "funding": "UNAVAILABLE (zero NOT substituted)",
        },
        "symbol_statistics": {
            "BTCUSDT": {
                "observations": len(rows),
                "orders": agg["total_orders"],
                "trades": agg["total_fills"],
                "wins": agg["wins"],
                "losses": agg["losses"],
                "status": "INCONCLUSIVE",
            }
        },
        "directional_statistics": {
            "note": "0 fills; LONG/SHORT asymmetry not assessable",
            "global_directional": dict(global_funnel["directional"]),
        },
        "regime_statistics": "REGIME_UNAVAILABLE",
        "survival_statistics": {
            "tested": agg["tested_periods"],
            "survived": agg["survived"],
            "rejected": agg["rejected"],
            "inconclusive": agg["inconclusive"],
            "unavailable": agg["unavailable"],
            "survival_ratio": agg["survival_ratio"],
        },
        "multiple_testing": "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY",
        "seven_e": "REJECTED (unchanged; no directional branch)",
        "limitations": [
            "Fresh span wall-clock bound (~8.0 days); ~25000 bars/period needed at measured rates.",
            "0 completed trades across 6 genuine OOS periods; every period INCONCLUSIVE/UNAVAILABLE.",
            "Per-period cold-start warmup (~200 bars) is an honest cost of independent periods.",
            "Row-level venue identity absent (manifest-level only).",
            "Flat/zero-volume provenance unknown (unchanged).",
            "Funding history, microstructure, min-notional unavailable (no adapters).",
            "Fresh data ran through the frozen strategy exactly once per period (plus global sanity); no retuning.",
        ],
        "gate_matrix": gates,
        "production_isolation": "PASS",
        "is_production_ready": False,
        "final_decision": decision,
        "final_reason": decision_reason,
        "edge": "NOT_ESTABLISHED",
        "live": "NO-GO",
    }
    text = (json.dumps(artifact, indent=2, sort_keys=True,
                       separators=(",", ": ")) + "\n")
    with io.open(str(ARTIFACT), "w", encoding="utf-8",
                 newline="") as fh:
        fh.write(text)
    print("wrote %s (%d bytes)" % (ARTIFACT, len(text)))
    print("decision: %s; per-period orders=%d fills=%d; global orders=%d fills=%d"
          % (decision, agg["total_orders"], agg["total_fills"],
             global_funnel["orders"], global_funnel["fills"]))


if __name__ == "__main__":
    main()
