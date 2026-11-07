"""Acquire a public Delta product snapshot from an EXPLICIT environment.

Unlike scripts/acquire_phase17_product_snapshot.py (pinned to the Global
endpoint and BTCUSDT), the REST host and symbol are explicit arguments and
the artifact records its full provenance. Public, credential-free,
read-only. Research/evidence use only -- never wired into execution.

Usage:
    python scripts/acquire_testnet_product_snapshot.py --base-url https://cdn-ind.testnet.deltaex.org --symbol BTCUSD --output research/captures/phase91/testnet_products.json --observed-label LABEL
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def acquire(*, base_url: str, symbol: str, observed_label: str) -> dict:
    if not base_url.strip() or not symbol.strip() or not observed_label.strip():
        raise ValueError("base_url, symbol and observed_label are required")
    import httpx
    response = httpx.get(base_url.rstrip("/") + "/v2/products", timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Delta products response was unsuccessful")
    entries = payload.get("result")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("INVALID_PRODUCT_CATALOG")
    matches = [e for e in entries if isinstance(e, dict) and e.get("symbol") == symbol]
    if not matches:
        raise RuntimeError("%s_NOT_LISTED" % symbol)
    if len(matches) != 1:
        raise RuntimeError("AMBIGUOUS_%s_PRODUCT" % symbol)
    return {
        "schema": "quantengine.delta-product-snapshot.v1",
        "venue": "delta",
        "endpoint": base_url.rstrip("/") + "/v2/products",
        "auth": "none",
        "state_changing": False,
        "observed_label": observed_label,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "catalog_population": len(entries),
        "catalog_sha256": hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":"),
                       default=str).encode()).hexdigest(),
        "symbol": symbol,
        "product": matches[0],
        "research_only": True,
        "is_production_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--observed-label", required=True)
    args = parser.parse_args(argv)
    snapshot = acquire(base_url=args.base_url, symbol=args.symbol,
                       observed_label=args.observed_label)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    import os
    os.replace(tmp, out)
    print("wrote %s" % out)
    print("catalog_sha256 %s" % snapshot["catalog_sha256"])
    print("product %s" % symbol_summary(snapshot))
    return 0


def symbol_summary(snapshot: dict) -> str:
    product = snapshot.get("product", {})
    return "%s/%s/%s" % (product.get("symbol"), product.get("contract_type"),
                         product.get("state"))


if __name__ == "__main__":
    raise SystemExit(main())
