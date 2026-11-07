"""Phase 11F-1 dataset lineage helpers (metadata only, D3 sealed).

D3 holdout candles are NEVER loaded here. `holdout_files()` returns
paths marked SEALED for audit display only; `load_holdout_candles()`
raises unconditionally so no candidate-selection, optimization, or
test path can accidentally evaluate the holdout before the final
freeze. Discovery helpers expose D0/D1 only; validation paths are
listed separately and never executed in 11F-1.
"""

from __future__ import annotations

import json
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent
BASE_DIR = RESEARCH_DIR.parent.parent


class SealedHoldoutError(RuntimeError):
    pass


# 11F-5 access audit: no code path in this repository reads, hashes,
# or loads D3 candle arrays, so read/hash/load stay 0 by construction;
# every refused holdout entry is counted in blocked (metadata only).
D3_ACCESS = {"read": 0, "hash": 0, "load": 0, "blocked": 0}


def spec() -> dict:
    return json.loads((RESEARCH_DIR / "datasets.json").read_text())


def discovery_files() -> list[str]:
    """D0/D1 discovery/development paths only — never D3."""
    doc = spec()
    out = [
        "data/history/BTCUSDT_1m_oos.json slice [0:500]",
        "research/phase11f/data/universe_D1_ETH.json slice [0:500]",
        "phase-7 BTCUSDT_1m_oos.json slice [500:7000]",
        "research/phase11f/data/universe_D1_ETH.json",
    ]
    # Structural guard: no holdout path may ever appear here.
    assert not any("D3" in p for p in out), "D3 leaked into discovery set"
    assert not any("oos_fresh" in p for p in out), "validation data leaked into discovery"
    _ = doc
    return out


def validation_files() -> list[str]:
    return [
        "phase-7 file slice [7000:10000]",
        "research/phase11e/data/oos_fresh.json",
        "research/phase11f/data/universe_D2_ETH.json",
    ]


def holdout_files() -> list[dict]:
    """SEALED holdout paths for audit display only (never loaded)."""
    return [
        {"path": "research/phase11f/data/universe_D3_BTC.json", "status": "SEALED_HOLDOUT"},
        {"path": "research/phase11f/data/universe_D3_ETH.json", "status": "SEALED_HOLDOUT"},
    ]


def is_sealed_holdout(path: str) -> bool:
    return "universe_D3_" in str(path) or "/D3" in str(path) or str(path).endswith("D3")


def assert_not_holdout(path: str) -> None:
    if is_sealed_holdout(path):
        D3_ACCESS["blocked"] += 1
        raise SealedHoldoutError("SEALED_HOLDOUT must not enter discovery: %s" % path)


def load_holdout_candles(*args, **kwargs):  # pragma: no cover - seal enforcement
    D3_ACCESS["blocked"] += 1
    raise SealedHoldoutError("D3 is SEALED until the final freeze; not openable in 11F-1")


def validate_lineage() -> list[str]:
    """Check tier/contamination metadata (no candle loading)."""
    errors: list[str] = []
    doc = spec()
    if doc.get("universe") != ["BTCUSDT", "ETHUSDT"]:
        errors.append("universe must be frozen [BTCUSDT, ETHUSDT]")
    if doc.get("timeframe") != "1m":
        errors.append("timeframe must be 1m")
    tiers = doc.get("tiers", {})
    for tier in ("D0_development", "D1_insample", "D2_validation", "D3_holdout"):
        if tier not in tiers:
            errors.append("missing tier %s" % tier)
    d3 = tiers.get("D3_holdout", {})
    if d3.get("role", "").upper().find("UNTOUCHED") < 0:
        errors.append("D3 role must declare UNTOUCHED")
    if "DATA_UNAVAILABLE" not in doc.get("orderflow", ""):
        errors.append("orderflow must declare DATA_UNAVAILABLE")
    if "PROXY_FEATURE" not in doc.get("orderflow", ""):
        errors.append("orderflow must label volume work PROXY_FEATURE")
    # Discovery/validation separation (path-level, no data read).
    for p in discovery_files():
        try:
            assert_not_holdout(p)
        except SealedHoldoutError as exc:
            errors.append(str(exc))
    for h in holdout_files():
        if h.get("status") != "SEALED_HOLDOUT":
            errors.append("holdout file must be SEALED_HOLDOUT: %s" % h)
    return errors
