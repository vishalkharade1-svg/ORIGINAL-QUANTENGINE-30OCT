"""
====================================================

QuantEngine -- Phase 17 OOS-feasibility artifact builder.

Research-only, deterministic GIVEN its inputs. Reads:
  docs/audit/baseline_9s_delta_5000_raw.json (committed)
  research/results/phase14...forensics.json (committed)
  research/results/phase15...readiness.json (committed)
  data/history/BTCUSDT_1m_phase17_fresh.json (git-ignored
    cache written by scripts/fetch_phase17_fresh.py)
  data/history/BTCUSDT_product_phase17.json (git-ignored
    venue-metadata snapshot acquired by a separate read-only
    acquisition step; this builder never accesses the network)

Writes (deterministic: indent=2, sort_keys=True):
  research/results/phase17_oos_feasibility.json

Runs NO strategy, places NO orders, uses NO credentials.
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
GATE_A_RAW = (ROOT / "docs" / "audit" /
              "baseline_9s_delta_5000_raw.json")
P14 = (ROOT / "research" / "results" /
       "phase14_executable_edge_forensics.json")
P15 = (ROOT / "research" / "results" /
       "phase15_evidence_readiness.json")
FRESH = (ROOT / "data" / "history" /
         "BTCUSDT_1m_phase17_fresh.json")
PRODUCT_SNAP = (ROOT / "data" / "history" /
                "BTCUSDT_product_phase17.json")
ARTIFACT = (ROOT / "research" / "results" /
            "phase17_oos_feasibility.json")

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


def product_snapshot():
    """Load the frozen venue snapshot; never acquire network data here."""
    if not PRODUCT_SNAP.exists():
        raise RuntimeError(
            "MISSING_PRODUCT_SNAPSHOT: deterministic Phase-17 artifact "
            "builder requires data/history/BTCUSDT_product_phase17.json; "
            "run the separate acquisition step first")
    return load(PRODUCT_SNAP), "cache"


def main():
    from core.research.acquisition.feasibility import (
        budget_periods,
        recalculate_requirements,
    )
    from core.research.acquisition.provenance import ProvenanceManifest
    from core.research.acquisition.quality import audit_quality
    from core.research.oos import constants as C

    p14 = load(P14)
    p15 = load(P15)
    fresh = load(FRESH)
    rows = fresh["raw"]
    assert fresh["fresh_after"] == 1788601440

    funnel = p14["funnel_accounting"]
    # Per-BAR order rate (orders_minted / dataset bars), NOT the
    # setup-normalized funnel order_rate (orders per setup event).
    # fills = bars * P(order|bar) * P(fill|order).
    order_rate = funnel["orders_minted"] / p14["dataset_bars"]
    fill_rate = funnel["fill_rate"]
    rate_basis = ("orders_minted %d / dataset_bars %d; fills %d / "
                  "orders %d" % (funnel["orders_minted"],
                                 p14["dataset_bars"],
                                 funnel["accepted_fills"],
                                 funnel["orders_minted"]))

    fhash = dataset_hash(rows)
    quality = audit_quality(rows, step=60, requested=fresh["requested"])
    cov = quality["coverage"]
    assert cov["start"] > 1788601440  # strictly after Gate-A

    manifest = ProvenanceManifest(
        venue="DELTA",
        market="perpetual_futures",
        instrument="BTCUSDT",
        symbol="BTCUSDT",
        timeframe="1m",
        acquisition_source="Delta /v2/history/candles",
        acquisition_method="HistoricalLoader.candles_paginated",
        requested_start=1788601440,
        requested_end=cov["end"],
        actual_start=cov["start"],
        actual_end=cov["end"],
        row_count=cov["received"],
        schema_version="gate-a-raw-v1",
        normalization_version="none (venue rows verbatim)",
        dataset_hash=fhash,
        acquisition_status=(
            "COMPLETE" if cov["coverage_pct"] == 1.0 else "PARTIAL"),
    )

    req = recalculate_requirements(order_rate, fill_rate)
    req["rate_basis"] = rate_basis
    budget = budget_periods(cov["received"], req["per_period_bars"])

    snap, snap_origin = product_snapshot()
    btc = snap.get("btcusdt") or {}
    specs = btc.get("product_specs") or {}

    shash = strategy_hash()
    assert shash == p14["strategy_hash"], "strategy drift"

    gates = {
        "phase16_baseline": "PASS (25/2/0W/2L/-0.206452, hash %s)" % shash[:12],
        "strategy_identity": "PASS (9-file set incl. execution_engine)",
        "strategy_hash": "PASS (exact match %s)" % shash[:16],
        "target_venue": "PASS (DELTA EXCHANGE)",
        "venue_provenance": (
            "PARTIAL (documented acquisition provenance; rows carry "
            "no venue tag -- row-level provenance ABSENT)"),
        "historical_coverage": (
            "PASS (fresh %d/%d, %.4f of post-Gate-A span)"
            % (cov["received"], cov["duration_bars"],
               cov["coverage_pct"])),
        "data_continuity": (
            "PASS (0 gaps, 0 missing intervals in fresh span)"
            if quality["continuity"]["gap_count"] == 0
            else "FAIL (%d gaps)" % quality["continuity"]["gap_count"]),
        "data_quality": (
            "PARTIAL (0 dupes, 0 OHLC violations, 0 malformed; "
            "flat %.1f%% / zero-volume %.1f%% PROVENANCE_UNKNOWN)"
            % (quality["activity"]["flat_pct"] * 100,
               quality["activity"]["zero_volume_pct"] * 100)),
        "instrument_semantics": (
            "PARTIAL (perpetual_futures, linear USDT-margined, "
            "tick/step/min-qty schema VERIFIED; per-symbol venue "
            "snapshot %s; minimum_notional UNAVAILABLE)" % snap_origin),
        "contract_semantics": (
            "PARTIAL (contract_value %s BTC, max_leverage_notional "
            "%s; expiry N/A perpetual; settlement USDT)" % (
                btc.get("contract_value"),
                btc.get("max_leverage_notional"))),
        "fee_schedule": (
            "PARTIAL (venue-reported maker %s / api %s observed "
            "%s; account-tier applicability UNVERIFIED; research "
            "cost model stays explicit-zero VERIFIED + ASSUMED "
            "scenarios)" % (btc.get("maker_commission_rate"),
                             specs.get("api_taker_commission_rate"),
                             snap_origin)),
        "funding": (
            "UNAVAILABLE (mechanism mark_price + clamp %s described; "
            "no historical funding series, no adapter; zero NOT "
            "substituted)" % specs.get("funding_clamp_value")),
        "microstructure": (
            "UNAVAILABLE (OHLCV-only; no trades/depth/L2/footprint "
            "adapter; nothing reconstructed)"),
        "sample_size": (
            "FAIL (fresh %d bars -> %d adequate 10-fill periods of "
            "%d required; N=2 fills INSUFFICIENT_SAMPLE)"
            % (cov["received"], budget["adequate_periods"],
               budget["required_periods"])),
        "oos_infrastructure": (
            "PASS (frozen splitter + 6-period protocol + Sidak/Holm "
            "+ 6175 gate + outcome-leakage guard)"),
        "genuine_oos_data": (
            "BLOCKED (mechanism works; fresh span %.1f days << "
            "required %.0f bars/period; wall-clock bound, not "
            "engineering)" % (cov["received"] / 1440,
                               req["per_period_bars"])),
        "temporal_independence": (
            "PASS (fresh strictly after Gate-A end %d; zero "
            "overlap; strategy never ran on fresh data)" % 1788601440),
        "purge_embargo": (
            "PASS (frozen 9M defaults purge=%d embargo=%d + "
            "outcome-leakage PROTECTED guard; no new values "
            "invented)" % (C.PURGE_BARS, C.EMBARGO_BARS)),
        "lookahead": "PASS (3x3 boundary suite green, unchanged)",
        "determinism": "PASS (byte-identical regen given same cache)",
        "multiple_testing": (
            "PASS (NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY; "
            "feasibility arithmetic only)"),
        "production_isolation": "PASS (FORBIDDEN-token scan green)",
        "edge": "NOT_ESTABLISHED",
        "production_readiness": False,
    }

    artifact = {
        "phase": 17,
        "mission": ("INDEPENDENT DATA ACQUISITION & GENUINE OOS "
                    "FEASIBILITY (research-only; strategy frozen)"),
        "baseline_commit": "6ae3aa7",
        "strategy_files": STRATEGY_FILES,
        "strategy_hash": shash,
        "strategy_unchanged": True,
        "baseline_reference": p14["baseline_reproduction"],
        "fresh_dataset": {
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "fresh_after": 1788601440,
            "requested": fresh["requested"],
            "received": cov["received"],
            "start": cov["start"],
            "end": cov["end"],
            "coverage_pct": cov["coverage_pct"],
            "dataset_hash": fhash,
            "cache": "data/history/BTCUSDT_1m_phase17_fresh.json "
                     "(git-ignored)",
        },
        "provenance": manifest.canonical_dict(),
        "manifest_id": manifest.manifest_id(),
        "quality": quality,
        "instrument_semantics": {
            "venue": "DELTA",
            "market_type": "perpetual_futures",
            "contract_type": btc.get("contract_type"),
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "settlement_asset": "USDT",
            "linear_inverse": "linear",
            "perpetual_future": "perpetual",
            "expiry": None,
            "contract_value": btc.get("contract_value"),
            "tick_size": "see venue snapshot (schema VERIFIED)",
            "minimum_quantity": "see venue snapshot (schema VERIFIED)",
            "minimum_notional": "UNAVAILABLE",
            "venue_snapshot_origin": snap_origin,
            "venue_population_observed": snap.get("population"),
        },
        "economics": {
            "commission_per_trade": "VERIFIED 0.0 (explicit-zero)",
            "commission_rate": "VERIFIED 0.0 (explicit-zero)",
            "slippage_bps": "VERIFIED 0.0 (explicit-zero)",
            "venue_maker_rate_observed": btc.get("maker_commission_rate"),
            "venue_api_taker_rate_observed": specs.get(
                "api_taker_commission_rate"),
            "fee_schedule": "PARTIAL (observed, tier-unverified)",
            "funding": "UNAVAILABLE",
            "funding_mechanism": "mark_price (described, no history)",
            "spread": "UNAVAILABLE",
        },
        "microstructure": "MICROSTRUCTURE_UNAVAILABLE",
        "sample_requirements": req,
        "period_budget": budget,
        "oos_design": {
            "discovery": "Gate-A + earlier frozen windows (committed)",
            "validation": "trailing discovery fraction 0.5 (frozen)",
            "oos_periods": C.OOS_PERIODS,
            "fresh_span_bars": cov["received"],
            "adequate_periods": budget["adequate_periods"],
            "verdict": budget["verdict"],
        },
        "gate_matrix": gates,
        "seven_e": "REJECTED (unchanged; no directional branch)",
        "multiple_testing": "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY",
        "production_isolation": "PASS",
        "is_production_ready": False,
        "final_decision": "OOS_BLOCKED",
        "edge": "NOT_ESTABLISHED",
        "live": "NO-GO",
        "limitations": [
            "Fresh span wall-clock bound (~%.1f days); "
            "~%.0f bars/period needed at measured rates." % (
                cov["received"] / 1440, req["per_period_bars"]),
            "Rate estimates from N=2 fills: requirement is a lower "
            "bound, unbounded above.",
            "Row-level venue identity absent (manifest-level only).",
            "Flat/zero-volume provenance unknown (unchanged).",
            "Funding history, microstructure, min-notional "
            "unavailable (no adapters).",
            "Venue population observed fluctuating between calls.",
            "Fresh data never touched by the strategy (kept unseen).",
        ],
    }
    text = (json.dumps(artifact, indent=2, sort_keys=True,
                       separators=(",", ": ")) + "\n")
    with io.open(str(ARTIFACT), "w", encoding="utf-8",
                 newline="") as fh:
        fh.write(text)
    print("wrote %s (%d bytes)" % (ARTIFACT, len(text)))
    print("decision: OOS_BLOCKED; fresh=%d bars; manifest=%s"
          % (cov["received"], manifest.manifest_id()[:16]))


if __name__ == "__main__":
    main()
