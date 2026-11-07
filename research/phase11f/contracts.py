"""Phase 11F-1 research contracts (architecture only, no execution).

Centralizes the machine-checkable contracts for hypotheses,
features, candidates, ablations, datasets, costs, and metrics.
All behavior reuses certified production/11E implementations;
this module only declares and validates — it never runs
candidate research, never opens D3 candles, never selects.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent
BASE_DIR = RESEARCH_DIR.parent.parent

RESEARCH_PROTOCOL_VERSION = "11F-1.0"
COST_PROTOCOL_VERSION = "11F-costs-A/B/C/D-v1"
EXECUTION_PROTOCOL_VERSION = "11F-exec-LIMIT_RETEST-v1"

# --------------------------------------------------
# Hypothesis contract (§4)
# --------------------------------------------------

HYPOTHESIS_REQUIRED_FIELDS = [
    "hypothesis_id",
    "name",
    "economic_rationale",
    "market_behavior_being_tested",
    "required_features",
    "entry_condition",
    "confirmation_condition",
    "stop_definition",
    "target_definition",
    "invalidation_condition",
    "maximum_wait_bars",
    "execution_model",
    "frozen_parameters",
    "allowed_research_parameters",
    "forbidden_optimization_dimensions",
    "required_data",
    "unavailable-data_behavior",
    "cost_assumptions",
    "expected_failure_modes",
    "status",
]

# CLASS D dimensions are never optimizable in any phase.
FORBIDDEN_CLASS_D = ["symbol", "timeframe", "costs", "holdout"]


def validate_hypotheses(doc: dict) -> list[str]:
    """Return a list of contract violations (empty = PASS)."""
    errors: list[str] = []
    hyps = doc.get("hypotheses", [])
    if len(hyps) != 8:
        errors.append("expected exactly 8 hypotheses, found %d" % len(hyps))
    seen = set()
    for h in hyps:
        hid = h.get("hypothesis_id", "?")
        if hid in seen:
            errors.append("duplicate hypothesis_id %s" % hid)
        seen.add(hid)
        for field in HYPOTHESIS_REQUIRED_FIELDS:
            if field not in h:
                errors.append("%s: missing field %s" % (hid, field))
        for dim in FORBIDDEN_CLASS_D:
            if dim not in h.get("forbidden_optimization_dimensions", []):
                errors.append(
                    "%s: forbidden dims must include CLASS D %r" % (hid, dim)
                )
        if h.get("status") != "RESEARCH_ONLY":
            errors.append("%s: status must be RESEARCH_ONLY" % hid)
        if "A/B/C/D" not in str(h.get("cost_assumptions", "")):
            errors.append("%s: cost_assumptions must reference A/B/C/D" % hid)
    if "RESEARCH_ONLY" not in str(doc.get("protocol", "")):
        errors.append("protocol must declare RESEARCH_ONLY / no promotion path")
    return errors


# --------------------------------------------------
# Feature contracts (§6) + proxy policy (§7)
# --------------------------------------------------
# Every feature maps bars[0..i] -> value[i] only.
# future_data_allowed is unconditionally FALSE.

FEATURE_CONTRACTS = {
    "atr14": {"required_history": 15, "lookback": 14, "future_data_allowed": False,
              "causal_rule": "Wilder ATR seeded from TR[1..14]; out[i] uses bars[0..i] only"},
    "rsi14": {"required_history": 15, "lookback": 14, "future_data_allowed": False,
              "causal_rule": "Wilder RSI; flat market yields 50.0; out[i] uses closes[0..i] only"},
    "ema": {"required_history": "period", "lookback": "period", "future_data_allowed": False,
            "causal_rule": "seeded with SMA(first period); None until seeded"},
    "sma": {"required_history": "period", "lookback": "period", "future_data_allowed": False,
            "causal_rule": "window bars[i-period+1..i] only"},
    "donchian": {"required_history": "period", "lookback": "period", "future_data_allowed": False,
                 "causal_rule": "highest-high/lowest-low of bars[i-period+1..i] only"},
    "swings": {"required_history": "left+right+1", "lookback": "left/right",
               "future_data_allowed": False,
               "causal_rule": "extreme at e published at e+right (confirmation lag); never back-dated"},
    "equal_levels": {"required_history": 50, "lookback": 50, "future_data_allowed": False,
                     "causal_rule": "confirmed swings only (causal); >=3 touches within tolerance"},
    "sweeps": {"required_history": 50, "lookback": 50, "future_data_allowed": False,
               "causal_rule": "wick beyond confirmed equal level + close back inside on bar i"},
    "displacement": {"required_history": 15, "lookback": "atr14", "future_data_allowed": False,
                     "causal_rule": "range[i] > mult*ATR14[i]"},
    "fvg_zones": {"required_history": 3, "lookback": 3, "future_data_allowed": False,
                  "causal_rule": "gap at i uses bars[i-2..i] only"},
    "order_block_before": {"required_history": 2, "lookback": "unbounded-past",
                           "future_data_allowed": False,
                           "causal_rule": "last opposite candle strictly before index (exclusive)"},
    "range_state": {"required_history": "period+min_hold", "lookback": "period/min_hold",
                    "future_data_allowed": False,
                    "causal_rule": "Donchian pair unchanged for min_hold bars; None until held"},
    "rvol_proxy": {"required_history": 20, "lookback": 20, "future_data_allowed": False,
                   "causal_rule": "PROXY_FEATURE: volume/SMA(volume); no bid/ask split exists",
                   "proxy": "PROXY_FEATURE"},
    "fib_retracement": {"required_history": "two confirmed swings", "lookback": "swing left/right",
                        "future_data_allowed": False,
                        "causal_rule": "levels at i use only swings confirmed at <= i; timestamp = max confirmations"},
    "fib_extension": {"required_history": "two confirmed swings", "lookback": "swing left/right",
                      "future_data_allowed": False,
                      "causal_rule": "levels at i use only swings confirmed at <= i; timestamp = max confirmations"},
}

PROXY_FEATURES = {"rvol_proxy"}
ORDERFLOW_STATUS = "DATA_UNAVAILABLE"


# --------------------------------------------------
# Candidate contract (§8)
# --------------------------------------------------

SIGNAL_REQUIRED_KEYS = ["direction", "entry", "stop", "take_profit", "setup_id"]

CANDIDATE_IDS = ["H11F-%03d" % i for i in range(1, 9)]

# Research-only execution channel. Production default is
# BREAKOUT_CONTINUATION-only; LIMIT_RETEST is activated via
# mock.patch inside research runs and restored afterwards.
RESEARCH_ENTRY_MODE = "LIMIT_RETEST"
PRODUCTION_ENTRY_MODES = ("BREAKOUT_CONTINUATION",)

FORBIDDEN_RESEARCH_IMPORTS = [
    "DeltaOrderExecutor",
    "BrokerEngine",
    "place_order",
    "submit_order",
    "LIVE_EXECUTE",
    "ALLOW_LIVE",
    "ccxt",
    "delta_rest",
    "DeltaExchange",
    "_require_auth",
    "DELTA_API_KEY",
    "DELTA_API_SECRET",
]


def validate_signal(sig: dict) -> list[str]:
    errors: list[str] = []
    for key in SIGNAL_REQUIRED_KEYS:
        if key not in sig:
            errors.append("signal missing key %s" % key)
    if sig.get("direction") not in ("BULLISH", "BEARISH"):
        errors.append("direction must be BULLISH/BEARISH, got %r" % sig.get("direction"))
    for key in ("entry", "stop", "take_profit"):
        try:
            float(sig.get(key))
        except (TypeError, ValueError):
            errors.append("signal key %s must be numeric" % key)
    if not str(sig.get("setup_id", "")):
        errors.append("setup_id must be non-empty")
    return errors


# --------------------------------------------------
# Ablation contract (§9): strict single removals only.
# --------------------------------------------------

ABLATIONS = {
    "H11F-002": [
        {"name": "full", "removed": None, "overrides": {}},
        {"name": "no-sweep", "removed": "sweep", "overrides": {"use_sweep": False}},
        {"name": "no-fvg", "removed": "fvg", "overrides": {"use_fvg": False}},
    ],
    "H11F-005": [
        {"name": "full", "removed": None, "overrides": {}},
        {"name": "no-sweep", "removed": "sweep", "overrides": {"use_sweep": False}},
    ],
    "H11F-007": [
        {"name": "full", "removed": None, "overrides": {}},
        {"name": "no-trend", "removed": "trend", "overrides": {"use_trend": False}},
        {"name": "no-fvg", "removed": "fvg", "overrides": {"use_fvg": False}},
    ],
}

ABLATION_INVARIANTS = ["identical data", "identical execution", "identical costs",
                       "identical risk", "single component removed"]


def validate_ablations() -> list[str]:
    errors: list[str] = []
    for hid, variants in ABLATIONS.items():
        names = [v["name"] for v in variants]
        if "full" not in names:
            errors.append("%s: ablation set must include full" % hid)
        for v in variants:
            if v["name"] == "full" and v["removed"] is not None:
                errors.append("%s full must remove nothing" % hid)
            if v["name"] != "full" and v["removed"] is None:
                errors.append("%s %s must name exactly one removed component"
                              % (hid, v["name"]))
    return errors


# --------------------------------------------------
# Cost semantics (§13): 11B/11E conventions, frozen.
# --------------------------------------------------

COST_SCENARIOS_11F = {
    "A": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0, "SLIPPAGE_BPS": 0.0},
    "B": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0005, "SLIPPAGE_BPS": 2.0},
    "C": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.00059, "SLIPPAGE_BPS": 5.0},
    "D": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.00118, "SLIPPAGE_BPS": 10.0},
}

# Funding is unmodeled for minute-scale perps holds (documented
# limitation, same as 11E). Represented explicitly as zero so
# net = gross - fees - slippage - funding holds exactly.
FUNDING_PER_TRADE = 0.0


def cost_breakdown(position_value: float, cost_key: str) -> dict:
    spec = COST_SCENARIOS_11F[cost_key]
    commission = spec["COMMISSION_PER_TRADE"] + position_value * spec["COMMISSION_RATE"]
    slippage = 2.0 * position_value * spec["SLIPPAGE_BPS"] / 10000.0
    return {"commission": float(commission), "slippage": float(slippage),
            "funding": float(FUNDING_PER_TRADE)}


def check_pnl_semantics(gross: float, commission: float, slippage: float,
                        funding: float, net: float, tol: float = 1e-9) -> bool:
    return abs((gross - commission - slippage - funding) - net) <= tol


# --------------------------------------------------
# Hash helpers (manifest §12)
# --------------------------------------------------

def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sha256_canonical(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())
