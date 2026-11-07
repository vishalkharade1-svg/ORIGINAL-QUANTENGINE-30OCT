"""Read-only reconciliation of the testnet authorization ledger against an exchange snapshot.

This utility never contacts an exchange and never places/cancels/retries orders.
Provide an exchange snapshot obtained through an independently reviewed read-only
process. Missing orders are not interpreted as cancelled or never accepted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.execution.testnet_durable_recovery import (
    DurableRecoveryError,
    reconcile_ledger_file,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, help="append-only testnet authorization ledger JSONL")
    parser.add_argument("--exchange-snapshot", required=True, help="JSON file containing an array of exchange order records")
    parser.add_argument("--snapshot-complete", action="store_true", help="assert that the supplied snapshot is complete for its stated query; does not prove order history completeness")
    parser.add_argument("--output", required=True, help="write the reconciliation report JSON to this path")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(Path(args.exchange_snapshot).read_text(encoding="utf-8"))
        if isinstance(snapshot, list):
            orders, fills = snapshot, []
        elif isinstance(snapshot, dict) and isinstance(snapshot.get("orders"), list) and isinstance(snapshot.get("fills", []), list):
            orders, fills = snapshot["orders"], snapshot.get("fills", [])
        else:
            raise DurableRecoveryError("exchange snapshot must be an array of orders or an object with orders and optional fills arrays")
        report = reconcile_ledger_file(args.ledger, orders, exchange_snapshot_complete=args.snapshot_complete, exchange_fills=fills)
        report["source_ledger"] = Path(args.ledger).name
        report["source_snapshot"] = Path(args.exchange_snapshot).name
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "REPORT_WRITTEN", "orders_reviewed": report["orders_reviewed"], "unresolved_count": report["unresolved_count"], "safe_to_resume_submissions": report["safe_to_resume_submissions"], "output": str(out)}, sort_keys=True))
        return 0 if report["unresolved_count"] == 0 else 2
    except (OSError, json.JSONDecodeError, DurableRecoveryError) as exc:
        print("RECONCILIATION_REFUSED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
