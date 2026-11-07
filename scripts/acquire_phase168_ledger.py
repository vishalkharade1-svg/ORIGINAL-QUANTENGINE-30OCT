"""Acquire Phase 168 authoritative ledger and execution records (read-only).

Pulls wallet balances, wallet transactions, fills, orders, and positions
from Delta India Testnet to provide the authoritative data backing the Phase 168
execution-economics reconciliation.

No orders are placed, modified, or cancelled. All requests are authenticated
read-only GETs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.exchanges.delta.delta_auth import DeltaSignedREST
from dotenv import dotenv_values


def load_credentials(root: Path) -> tuple[str, str]:
    # Check parent .env first (standard operator credential store) then root .env
    parent_env = root.parent / ".env"
    local_env = root / ".env"
    env_path = parent_env if parent_env.exists() else local_env
    if not env_path.exists():
        raise FileNotFoundError(f"No .env file found at {parent_env} or {local_env}")

    vals = dotenv_values(env_path)
    api_key = (
        vals.get("DELTA_INDIA_TESTNET_API_KEY")
        or vals.get("DELTA_API_KEY")
        or os.environ.get("DELTA_INDIA_TESTNET_API_KEY")
        or os.environ.get("DELTA_API_KEY")
        or ""
    )
    api_secret = (
        vals.get("DELTA_INDIA_TESTNET_API_SECRET")
        or vals.get("DELTA_API_SECRET")
        or os.environ.get("DELTA_INDIA_TESTNET_API_SECRET")
        or os.environ.get("DELTA_API_SECRET")
        or ""
    )
    if not (api_key and api_secret):
        raise ValueError("Missing Delta Testnet credentials in .env")
    return api_key, api_secret


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "research" / "captures" / "phase168_ledger",
        help="Directory to save raw capture records",
    )
    args = parser.parse_args()

    api_key, api_secret = load_credentials(REPO_ROOT)
    client = DeltaSignedREST(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://cdn-ind.testnet.deltaex.org",
    )

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching /v2/wallet/balances...")
    balances = client.get("/v2/wallet/balances")
    (out_dir / "balances.json").write_text(
        json.dumps(balances, indent=2, sort_keys=True), encoding="utf-8"
    )

    print("Fetching /v2/wallet/transactions...")
    txns = client.get("/v2/wallet/transactions", params={"page_size": 100})
    # Store transactions list in wallet_100.json (matching phase147/phase153 format)
    txn_list = txns.get("result", [])
    (out_dir / "wallet_100.json").write_text(
        json.dumps(txn_list, indent=2, sort_keys=True), encoding="utf-8"
    )

    print("Fetching /v2/fills...")
    fills = client.get("/v2/fills", params={"page_size": 100, "symbol": "BTCUSD"})
    fill_list = fills.get("result", [])
    (out_dir / "fills_100.json").write_text(
        json.dumps(fill_list, indent=2, sort_keys=True), encoding="utf-8"
    )

    print("Fetching /v2/orders (closed)...")
    orders = client.get(
        "/v2/orders", params={"page_size": 100, "product_id": 84, "state": "closed"}
    )
    order_list = orders.get("result", [])
    (out_dir / "orders_100.json").write_text(
        json.dumps(order_list, indent=2, sort_keys=True), encoding="utf-8"
    )

    print("Fetching /v2/positions for BTCUSD (84) and ADAUSD (101760)...")
    positions = {}
    for pid, sym in [(84, "BTCUSD"), (101760, "ADAUSD")]:
        try:
            pos = client.get("/v2/positions", params={"product_id": pid})
            positions[sym] = pos.get("result", {})
        except Exception as exc:
            positions[sym] = {"error": str(exc)}
    (out_dir / "positions.json").write_text(
        json.dumps(positions, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"Captured {len(txn_list)} wallet txns, {len(fill_list)} fills, {len(order_list)} orders.")
    print(f"Artifacts written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
