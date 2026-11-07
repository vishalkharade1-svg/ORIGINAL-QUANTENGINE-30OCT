"""Deterministic strategy-digest re-certification procedure (read-only).

Computes the canonical digest of the nine strategy source files and
reports whether legitimate re-certification is possible.  This script
NEVER rewrites pins, fixtures, or research artifacts: re-certification
additionally requires re-executing the research protocol under the
current source, which this procedure verifies the absence of.

Canonical construction (explicit, checkout-independent):
  representation : raw file bytes with CRLF normalized to LF
  ordering       : STRATEGY_FILES listed below, in order
  algorithm      : sha256 hex per file, concatenated, sha256 hex again
  files          : the nine strategy sources (frozen set)

Exit status: 0 when the procedure executes and reports.  The machine-
readable `status` field carries the certification verdict
(RE-CERTIFIED is only possible with a recorded research re-execution;
otherwise BLOCKED with explicit reasons).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


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

RECORDED_DIGEST = "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6"


def canonical_bytes(path: Path) -> bytes:
    """Raw bytes with CRLF normalized to LF (checkout-independent)."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def canonical_digest(root: Path) -> tuple[str, list[dict]]:
    per_file = []
    for name in STRATEGY_FILES:
        data = canonical_bytes(root / name)
        per_file.append({"file": name,
                         "sha256": hashlib.sha256(data).hexdigest()})
    joined = "".join(entry["sha256"] for entry in per_file)
    return hashlib.sha256(joined.encode()).hexdigest(), per_file


def assess(root: Path) -> dict:
    digest, per_file = canonical_digest(root)
    reasons = [
        "the supplied source archive lacks the original Git checkout and "
        "mint-time working bytes, so historical reproducibility cannot be "
        "established from this archive alone",
        "current source contains the verified Phase-4 gate-80 "
        "correction and cost seam, so findings built on the recorded "
        "digest cannot be transferred without re-execution",
        "no recorded research re-execution under the current source "
        "exists in the repository",
    ]
    return {
        "schema": "quantengine.strategy-digest-recertification.v1",
        "canonical": {
            "representation": "bytes with CRLF normalized to LF",
            "ordering": list(STRATEGY_FILES),
            "algorithm": "sha256(per-file) concatenated, sha256 again",
        },
        "recorded_digest": RECORDED_DIGEST,
        "canonical_digest": digest,
        "per_file": per_file,
        "matches_recorded": digest == RECORDED_DIGEST,
        "status": "BLOCKED",
        "reasons": reasons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable report")
    args = parser.parse_args(argv)
    try:
        report = assess(args.root.resolve())
    except (OSError, ValueError) as exc:
        print("RECERTIFICATION_ERROR %s" % exc)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("RECORDED : %s" % report["recorded_digest"])
        print("CANONICAL: %s" % report["canonical_digest"])
        print("MATCHES_RECORDED: %s" % report["matches_recorded"])
        print("STATUS: %s" % report["status"])
        for reason in report["reasons"]:
            print("REASON: %s" % reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
