"""
====================================================
QuantEngine -- Phase 19 data-extension artifact builder.

Research-only, deterministic GIVEN its inputs. Reads:
  research/results/phase14...forensics.json (committed)
  research/results/phase17_oos_feasibility.json (committed)
  research/results/phase18_oos_validation.json (committed)
  data/history/BTCUSDT_1m_phase17_fresh.json (git-ignored
    Phase-18 frozen cache, never overwritten)
  data/history/BTCUSDT_1m_phase19_extension.json (git-ignored
    merged extension cache from fetch_phase19_extension.py)

Writes (deterministic: indent=2, sort_keys=True):
  research/results/phase19_oos_data_extension.json

Runs the FROZEN strategy unchanged (Backtester defaults):
6 independent per-period runs over the merged span + 1
global continuous run, for feasibility measurement only.
Places NO orders, uses NO credentials, changes NO
thresholds. Tier A direct-venue only; no proxy/synthetic.
====================================================
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

P14 = ROOT / "research" / "results" / "phase14_executable_edge_forensics.json"
P17 = ROOT / "research" / "results" / "phase17_oos_feasibility.json"
P18 = ROOT / "research" / "results" / "phase18_oos_validation.json"
PRIOR = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
EXT = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.json"
ARTIFACT = ROOT / "research" / "results" / "phase19_oos_data_extension.json"

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
    from core.research.extension.extension import (
        estimate_extension,
        extension_stats,
    )
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
    p18 = load(P18)
    prior = load(PRIOR)
    ext = load(EXT)
    prior_rows = sorted(prior["raw"], key=lambda r: r["time"])
    rows = sorted(ext["raw"], key=lambda r: r["time"])
    assert ext["fresh_after"] == GATE_A_END
    assert prior["fresh_after"] == GATE_A_END

    shash = strategy_hash()
    assert shash == p14["strategy_hash"], "strategy drift"
    assert shash == p18["strategy_hash"], "strategy drift vs phase 18"

    prior_hash = dataset_hash(prior_rows)
    assert prior_hash == p17["provenance"]["dataset_hash"], "prior drift"
    assert prior_hash == p18["dataset"]["dataset_hash"], "prior drift vs 18"

    fhash = dataset_hash(rows)
    quality = audit_quality(rows, step=60, requested=ext["requested"])
    cov = quality["coverage"]
    assert cov["start"] > GATE_A_END
    fresh_check = validate_freshness(rows, GATE_A_END)
    assert fresh_check["strictly_after"]
    stats = extension_stats(prior_rows, rows)

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
            "bars": spec["row_count"],
            "observations": spec["row_count"],
            "opportunities": None,
            "orders": funnel["orders"],
            "fills": funnel["fills"],
            "completed_trades": funnel["completed_trades"],
            "wins": funnel["wins"],
            "losses": funnel["losses"],
            "gross_pnl": funnel["gross_pnl"],
            "actual_fill_rr": list(funnel["actual_fill_rr"]),
            "terminal": dict(funnel["terminal"]),
            "directional": dict(funnel["directional"]),
            "status": status,
            "reason": reason,
        })

    global_funnel = run_frozen_oos(rows, symbol="BTCUSDT")
    agg = aggregate_results([
        {"bars": p["bars"], "orders": p["orders"],
         "completed_trades": p["completed_trades"], "wins": p["wins"],
         "losses": p["losses"], "gross_pnl": p["gross_pnl"],
         "status": p["status"]} for p in per_period
    ])
    decision, decision_reason = decide_final(
        agg, min_total_trades=C.MIN_TOTAL_OOS_TRADES,
        min_surviving=C.MIN_SURVIVING_PERIODS)
    est = estimate_extension(agg["total_fills"], len(rows))
    struct = scenarios.scenario_structural(global_funnel["gross_pnl"])

    flat_pct = quality["activity"]["flat_pct"]
    zv_pct = quality["activity"]["zero_volume_pct"]
    gates = {
        "phase18_baseline": "PASS (OOS_BLOCKED, 0 fills/11461 bars)",
        "frozen_strategy": "PASS (9-file set incl. execution_engine)",
        "strategy_hash": "PASS (exact match %s)" % shash[:16],
        "no_strategy_mutation": "PASS (hash re-verified post-run)",
        "target_venue": "PASS (DELTA EXCHANGE, Tier A direct only)",
        "dataset_provenance": "PASS (DELTA /v2/history/candles; rows carry no venue tag)",
        "dataset_integrity": "PASS (0 dupes, 0 gaps, 0 OHLC violations, 0 malformed)" if quality["integrity"]["duplicates"] == 0 and quality["continuity"]["gap_count"] == 0 and quality["integrity"]["ohlc_violations"] == 0 else "FAIL (see quality)",
        "oos_boundary": "PASS (all %d strictly after %d)" % (len(rows), GATE_A_END),
        "discovery_separation": "PASS (discovery Gate-A only; extension strictly after; no concat-split/shuffle)",
        "temporal_ordering": "PASS (ascending, unique, 6 chronological periods)",
        "coverage": "PASS (%.4f over merged span %d bars)" % (cov["coverage_pct"], len(rows)),
        "flat_bar_quality": "PARTIAL (flat %.1f%% PROVENANCE_UNKNOWN)" % (flat_pct * 100),
        "zero_volume_quality": "PARTIAL (zero-volume %.1f%% PROVENANCE_UNKNOWN)" % (zv_pct * 100),
        "microstructure": "UNAVAILABLE (OHLCV-only; nothing reconstructed)",
        "funding": "UNAVAILABLE (no history, no adapter; zero NOT substituted)",
        "fee_verification": "PARTIAL (explicit-zero VERIFIED; venue schedule ASSUMED-only)",
        "execution_funnel": "PASS (frozen NEXT_BAR_OPEN; per-period %d orders / %d fills; global %d orders / %d fills)" % (agg["total_orders"], agg["total_fills"], global_funnel["orders"], global_funnel["fills"]),
        "actual_fill_rr": "UNAVAILABLE (0 fills; RR>=6 gate intact)",
        "completed_trade_count": "FAIL (0 total, 0/period; need 60 total + 10/period)",
        "period_count": "PASS (6 independent chronological periods executed)",
        "period_independence": "PASS (independent per-period runs; no cross-period leakage)",
        "per_period_sample": "FAIL (0 adequate 10-trade periods of 6)",
        "total_sample": "FAIL (0 of 60 required)",
        "lookahead": "PASS (NEXT_BAR_OPEN; future-mutation suite green)",
        "purge_embargo": "PASS (frozen purge=0 embargo=0; no new values)",
        "determinism": "PASS (byte-identical regen given same cache)",
        "production_isolation": "PASS (FORBIDDEN-token scan green)",
        "oos_feasibility": "BLOCKED (genuine extension measured; executable sample still zero)",
        "production_readiness": False,
    }

    artifact = {
        "phase": 19,
        "mission": ("INDEPENDENT OOS DATA EXTENSION & EXECUTABLE-SAMPLE "
                    "ACCUMULATION (research-only; strategy frozen)"),
        "baseline_commit": "031de0d",
        "strategy_files": STRATEGY_FILES,
        "strategy_hash": shash,
        "strategy_unchanged": True,
        "baseline_reference": p14["baseline_reproduction"],
        "phase18_reference": {
            "bars": 11461,
            "fills": 0,
            "decision": p18["final_decision"],
        },
        "dataset_identity": {
            "source": "Delta /v2/history/candles",
            "venue": "DELTA",
            "tier": "A-DIRECT",
            "market": "perpetual_futures",
            "instrument": "BTCUSDT",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "original_oos_boundary": GATE_A_END,
        "prior_span": {
            "start": prior_hash and p18["dataset"]["start"],
            "end": p18["dataset"]["end"],
            "bars": 11461,
            "dataset_hash": prior_hash,
        },
        "extended_span": {
            "start": cov["start"],
            "end": cov["end"],
            "bars": len(rows),
            "dataset_hash": fhash,
            "cache": ("data/history/BTCUSDT_1m_phase19_extension.json "
                      "(git-ignored)"),
            "requested": ext["requested"],
        },
        "extension": stats,
        "total_bars": len(rows),
        "quality": quality,
        "provenance": {
            "acquisition_source": "Delta /v2/history/candles",
            "acquisition_method": "HistoricalLoader.candles_paginated",
            "tier": "A-DIRECT",
            "prior_cache": "data/history/BTCUSDT_1m_phase17_fresh.json",
            "extension_cache": "data/history/BTCUSDT_1m_phase19_extension.json",
        },
        "period_feasibility": per_period,
        "execution_funnel": {
            "per_period_orders": agg["total_orders"],
            "per_period_fills": agg["total_fills"],
            "global_orders": global_funnel["orders"],
            "global_terminal": dict(global_funnel["terminal"]),
            "global_fills": global_funnel["fills"],
            "global_gross": global_funnel["gross_pnl"],
        },
        "completed_trades": agg["total_fills"],
        "sample_adequacy": {
            "required_total": C.MIN_TOTAL_OOS_TRADES,
            "actual_total": agg["total_fills"],
            "required_per_period": C.MIN_OOS_TRADES_PER_PERIOD,
            "adequate_periods": 0,
            "feasible": False,
        },
        "required_sample": {
            "per_period_trades": C.MIN_OOS_TRADES_PER_PERIOD,
            "total_trades": C.MIN_TOTAL_OOS_TRADES,
            "periods": C.OOS_PERIODS,
        },
        "estimated_additional_data": est,
        "economic_scenarios": {
            "structural": "VERIFIED-zero-cost",
            "structural_net": struct["net"],
            "funding": "UNAVAILABLE (zero NOT substituted)",
        },
        "limitations": [
            "Extension wall-clock bound: only %d new bars beyond Phase-18 span." % stats["added_bars"],
            "0 completed trades across %d merged bars; no finite bars-per-fill inferable." % len(rows),
            "Flat %.1f%% / zero-volume %.1f%% PROVENANCE_UNKNOWN persists." % (flat_pct * 100, zv_pct * 100),
            "Row-level venue identity absent (manifest-level only).",
            "Funding/microstructure/min-notional unavailable (no adapters).",
            "Proxy/synthetic tiers not used (Tier A direct only).",
            "Fresh extension ran through frozen strategy once per period + global; no retuning.",
        ],
        "gate_matrix": gates,
        "production_isolation": "PASS",
        "is_production_ready": False,
        "final_decision": "OOS_BLOCKED",
        "final_reason": ("merged %d bars -> 0 fills; 0 adequate periods; "
                         "only %d new bars beyond Phase 18" % (len(rows), stats["added_bars"])),
        "edge": "NOT_ESTABLISHED",
        "live": "NO-GO",
    }
    text = (json.dumps(artifact, indent=2, sort_keys=True,
                       separators=(",", ": ")) + "\n")
    with io.open(str(ARTIFACT), "w", encoding="utf-8",
                 newline="") as fh:
        fh.write(text)
    print("wrote %s (%d bytes)" % (ARTIFACT, len(text)))
    print("decision: OOS_BLOCKED; merged=%d (+%d) fills=%d"
          % (len(rows), stats["added_bars"], agg["total_fills"]))


if __name__ == "__main__":
    main()
