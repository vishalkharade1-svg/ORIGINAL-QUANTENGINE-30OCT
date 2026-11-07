"""Acquire the explicit Phase-17 Delta product snapshot.

This is the network-facing acquisition step. It is research-only, public,
credential-free, and read-only. The deterministic artifact builder must never
call this script implicitly.

Usage:
    python scripts/acquire_phase17_product_snapshot.py --observed-label LABEL

LABEL is caller-supplied so acquisition never depends on wall-clock time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.exchanges.delta.delta_products import DeltaProducts  # noqa: E402

OUTPUT = ROOT / "data" / "history" / "BTCUSDT_product_phase17.json"


def acquire(observed_label: str, *, output: Path = OUTPUT) -> dict:
    if not observed_label.strip():
        raise ValueError("observed_label must be non-empty")

    catalog = DeltaProducts().download()
    entries = catalog.get("result", catalog) if isinstance(catalog, dict) else catalog
    if not isinstance(entries, list):
        raise RuntimeError("INVALID_PRODUCT_CATALOG")

    matches = [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("symbol") == "BTCUSDT"
    ]
    if not matches:
        raise RuntimeError("BTCUSDT_NOT_LISTED")
    if len(matches) != 1:
        raise RuntimeError("AMBIGUOUS_BTCUSDT_PRODUCT")

    product = matches[0]
    catalog_sha256 = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    snapshot = {
        "schema": "quantengine.delta-phase17-product-snapshot.v1",
        "venue": "DELTA",
        "endpoint": "https://api.delta.exchange/v2/products",
        "auth": "none",
        "state_changing": False,
        "observed_label": observed_label,
        "catalog_population": len(entries),
        "catalog_sha256": catalog_sha256,
        "btcusdt": product,
        "research_only": True,
        "is_production_ready": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, output)
    return snapshot


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-label", required=True)
    args = parser.parse_args(argv)
    snapshot = acquire(args.observed_label)
    print("wrote %s" % OUTPUT)
    print("catalog_sha256 %s" % snapshot["catalog_sha256"])
    print("symbol %s" % snapshot["btcusdt"].get("symbol"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
