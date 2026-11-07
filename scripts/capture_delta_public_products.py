"""Capture genuine Delta public product metadata (credential-free).

Operator evidence script (run directly, never imported by tests):

    python scripts/capture_delta_public_products.py [SYMBOL ...]

What it does (read-only, zero credentials, zero state change):
  * GETs the PUBLIC /v2/products catalog via DeltaProducts (the same
    loader the contract registry consumes — no auth is sent because
    DeltaREST carries no credentials at all).
  * Extracts the FULL raw venue entries for the requested symbols
    (default: the .env SYMBOLS universe, read as configuration —
    never credentials).
  * Writes a sanitized, provenance-labeled artifact under
    data/fixtures/delta/ following the observed_* fixture
    conventions (endpoint, symbol list, catalog size + catalog
    sha256, per-symbol raw entries, limitations).

What it does NOT do:
  * No authentication, no API key/secret handling, no signatures.
  * No private endpoints, no orders, no state-changing calls.
  * No venue values invented: symbols absent from the catalog are
    recorded as NOT_LISTED with no fabricated terms.
  * The artifact is PARSER/INGESTION evidence only. It does not
    authorize live execution and is never wired into sizing.

Artifact identity: filename carries the capture-session date label
(prior-phase convention); the artifact embeds a sha256 over the
canonical (sorted-keys) sanitized content as its deterministic
evidence ID. No UUIDs, no randomness.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.exchanges.delta.delta_products import DeltaProducts  # noqa: E402

ENDPOINT = "https://api.delta.exchange"
CATALOG_PATH = "/v2/products"
ARTIFACT_SCHEMA = "quantengine.delta-public-products.v1"

# Fields copied verbatim from each raw venue entry. This allowlist
# is the sanitization boundary: anything outside it is dropped, so
# even a surprising venue field can never smuggle sensitive or
# oversized content into the artifact.
KEPT_FIELDS = (
    "id",
    "symbol",
    "contract_type",
    "contract_value",
    "contract_value_precision",
    "contract_unit_currency",
    "tick_size",
    "minimum_order_size",
    "maximum_leverage",
    "maker_commission_rate",
    "taker_commission_rate",
    "price_precision",
    "underlying_asset",
    "strike_price",
    "settlement_asset",
    "settling_asset",
    "quote_asset",
    "product_state",
    "state",
    "trading_status",
)


def _sanitize_entry(raw: dict) -> dict:
    clean: dict = {}
    for key in KEPT_FIELDS:
        if key in raw:
            value = raw[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean[key] = value
            elif isinstance(value, dict):
                clean[key] = {
                    k: v for k, v in value.items()
                    if isinstance(v, (str, int, float, bool))
                    or v is None
                }
    return clean


def _default_symbols() -> list[str]:
    raw = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT")
    return [s.strip() for s in raw.split(",") if s.strip()]


def main(argv: list[str]) -> int:
    symbols = [s.strip() for s in argv if s.strip()] or _default_symbols()

    catalog = DeltaProducts().download()
    entries = catalog.get("result", catalog) if isinstance(catalog, dict) else catalog
    if not isinstance(entries, list):
        print("unexpected catalog shape", file=sys.stderr)
        return 2

    catalog_canonical = json.dumps(entries, sort_keys=True, default=str)
    catalog_sha256 = hashlib.sha256(
        catalog_canonical.encode("utf-8")).hexdigest()

    by_symbol = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("symbol"):
            by_symbol[str(entry["symbol"])] = entry

    products = {}
    for symbol in symbols:
        raw = by_symbol.get(symbol)
        if raw is None:
            products[symbol] = {"listed": False,
                                "status": "NOT_LISTED"}
        else:
            products[symbol] = {"listed": True,
                                "entry": _sanitize_entry(raw)}

    observed = datetime.now(timezone.utc).strftime("%Y%m%d")
    content = {
        "schema": ARTIFACT_SCHEMA,
        "endpoint": ENDPOINT,
        "catalog_path": CATALOG_PATH,
        "auth": "none (public credential-free capture)",
        "state_changing": False,
        "symbols_requested": symbols,
        "catalog_size": len(entries),
        "catalog_sha256": catalog_sha256,
        "observed_date": observed,
        "products": products,
        "limitations": [
            "public catalog snapshot: parser/ingestion evidence only",
            "never wired into sizing, execution, or live authority",
            "fee fields (maker/taker commission rates) are venue-",
            "provided where present; funding, slippage, and spread",
            "are NOT provided by this endpoint",
            "settlement semantics limited to venue asset fields",
            "absent symbols recorded as NOT_LISTED, never defaulted",
        ],
    }
    evidence_id = hashlib.sha256(
        json.dumps(content, sort_keys=True,
                   default=str).encode("utf-8")).hexdigest()
    content["evidence_id"] = "sha256:" + evidence_id

    out_dir = ROOT / "data" / "fixtures" / "delta"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("observed_global_products_public_%s.json"
                      % observed)
    path.write_text(json.dumps(content, indent=2, sort_keys=True)
                    + "\n", encoding="utf-8")
    print("wrote %s (%d bytes, %d/%d symbols listed)"
          % (path, path.stat().st_size,
             sum(1 for p in products.values() if p.get("listed")),
             len(products)))
    print("evidence_id sha256:%s" % evidence_id)
    print("catalog_sha256 %s" % catalog_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
