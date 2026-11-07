"""QuantEngine Versioned Strategy & Runtime Identity Architecture (Phase 165).

Decouples the quantitative strategy alpha thesis from runtime and simulation
scaffolding, while preserving historical cryptographic pins intact.

Historical Context:
  Phase 14 pinned a 9-file composite digest:
    c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6
  which concatenated 6 strategy/risk logic files with 3 execution/runtime files.
  Any bugfix or refactor to paper trading, backtest loops, or accounting
  unavoidably altered the 9-file digest, even when quantitative alpha rules
  were untouched.

Phase 165 Architecture:
  1. Alpha Strategy Core (v1.1):
     - core/execution/entry_model.py
     - core/setup/trade_setup_builder.py
     - core/setup/decision_engine.py
     - core/execution/execution_engine.py
     - core/risk/risk_engine.py
     - config/risk_settings.py

  2. Runtime & Execution Infrastructure (v1.1):
     - core/backtesting/accounting.py
     - backtesting/backtester.py
     - core/paper_trading/paper_trading_engine.py
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


HISTORICAL_PHASE14_STRATEGY_HASH = (
    "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6"
)

# Frozen-research runtime isolation (Phase 22). Historical OOS replay
# artifacts (Phases 14/17/18/19) were generated under the Phase-14 1.0
# runtime semantics, in which the only RR constraint was
# config.risk_settings.MIN_RISK_REWARD. The runtime policy layer
# (trading_policy min/max RR bounds, exit-mode geometry) is a
# product-execution authority and must never silently alter the
# semantics of a frozen research replay. While the flag below is "1",
# policy-driven runtime gates must yield to the frozen-era gate.
FROZEN_OOS_ENV = "QUANTENGINE_FROZEN_OOS"

# Frozen-era RR floor (Phase-14 1.0 semantics). This is governance data
# of the research identity layer, deliberately NOT read from
# config.risk_settings (whose MIN_RISK_REWARD the Phase-99/100 policy
# guards allow only as unconsumed governance data in production
# sources). While a frozen OOS replay is active, executable gates may
# consult this value; outside frozen replays the runtime policy layer
# remains the sole fill-path authority.
FROZEN_ERA_MIN_RR = 6.0


def frozen_runtime_requested() -> bool:
    """True while a frozen OOS replay is executing in this process."""
    return os.environ.get(FROZEN_OOS_ENV, "") == "1"

STRATEGY_CORE_FILES = [
    "core/execution/entry_model.py",
    "core/setup/trade_setup_builder.py",
    "core/setup/decision_engine.py",
    "core/execution/execution_engine.py",
    "core/risk/risk_engine.py",
    "config/risk_settings.py",
]

RUNTIME_INFRA_FILES = [
    "core/backtesting/accounting.py",
    "backtesting/backtester.py",
    "core/paper_trading/paper_trading_engine.py",
]

LEGACY_9_FILES = [
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


def canonical_file_bytes(path: Path) -> bytes:
    """Normalize CRLF to LF to produce deterministic, checkout-independent digests."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def compute_file_digest(path: Path, normalize_lf: bool = True) -> str:
    data = canonical_file_bytes(path) if normalize_lf else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def normalize_rel_path(rel: str) -> str:
    """Validate and normalize relative paths, preventing traversal, empty strings, and backslash variance."""
    if not isinstance(rel, str) or not rel.strip():
        raise ValueError(f"Strategy file path must be a non-empty string: {rel!r}")
    norm = os.path.normpath(rel.strip()).replace("\\", "/")
    parts = Path(norm).parts
    if ".." in parts or norm.startswith("../") or norm == "..":
        raise ValueError(f"Strategy file path must be relative without traversal: {rel}")
    if Path(norm).is_absolute() or os.path.isabs(norm):
        raise ValueError(f"Strategy file path must be relative: {rel}")
    return norm


def compute_composite_digest(root: Path, file_list: list[str], normalize_lf: bool = True) -> tuple[str, list[dict[str, str]]]:
    if not file_list:
        raise ValueError("file_list must be non-empty")

    normalized_files = [normalize_rel_path(rel) for rel in file_list]
    if len(normalized_files) != len(set(normalized_files)):
        raise ValueError("Duplicate file entries detected in file_list")

    details = []
    for norm in normalized_files:
        target = root / norm
        if not target.is_file():
            raise FileNotFoundError(f"Strategy file not found or not a regular file: {norm}")
        h = compute_file_digest(target, normalize_lf=normalize_lf)
        details.append({"file": norm, "sha256": h})
    joined = "".join(item["sha256"] for item in details)
    composite = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return composite, details


def get_versioned_identities(root: Path) -> dict:
    root = Path(root).resolve()
    core_hash, core_files = compute_composite_digest(root, STRATEGY_CORE_FILES, normalize_lf=True)
    infra_hash, infra_files = compute_composite_digest(root, RUNTIME_INFRA_FILES, normalize_lf=True)
    legacy9_lf, legacy9_files = compute_composite_digest(root, LEGACY_9_FILES, normalize_lf=True)
    legacy9_raw, _ = compute_composite_digest(root, LEGACY_9_FILES, normalize_lf=False)

    return {
        "schema": "quantengine.strategy-identity.v2",
        "historical_phase14_pinned_hash": HISTORICAL_PHASE14_STRATEGY_HASH,
        "strategy_core": {
            "version": "1.1-phase4-corrected",
            "sha256": core_hash,
            "files": core_files,
            "description": "Pure quantitative strategy setup, decision gates, entry models, and risk rules."
        },
        "runtime_infrastructure": {
            "version": "1.1-phase164-hardened",
            "sha256": infra_hash,
            "files": infra_files,
            "description": "Execution simulation, accounting calculations, and paper trading engine."
        },
        "composite_legacy_9_files": {
            "canonical_lf_sha256": legacy9_lf,
            "raw_disk_sha256": legacy9_raw,
            "files": legacy9_files
        }
    }
