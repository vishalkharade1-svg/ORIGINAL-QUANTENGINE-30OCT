"""Deterministic Phase 169 Execution Economics Reconciliation.

Reconciles the completed testnet order experiment against authoritative venue records:
1. REST fills (research/captures/phase167_recon/rest_fills.json)
2. Private WebSocket fills (research/captures/phase167_recon/private_ws_frames.json)
3. Top-of-book L2 friction (research/captures/phase167_recon/l2/)
4. Authoritative wallet ledger (research/captures/phase168_ledger/wallet_100.json)
5. Authoritative wallet balances (research/captures/phase168_ledger/balances.json)
6. Positions endpoint (research/captures/phase168_ledger/positions.json)

Outputs a certified JSON artifact with explicit component-level verifications at:
research/results/phase169_execution_economics_reconciliation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.reconciliation.execution_economics_verifier import ExecutionEconomicsVerifier


def run_reconciliation(root: Path) -> dict:
    verifier = ExecutionEconomicsVerifier(root)
    return verifier.run_full_reconciliation(phase=169)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "research" / "results" / "phase169_execution_economics_reconciliation.json",
        help="Path to save reconciliation JSON",
    )
    args = parser.parse_args()

    result = run_reconciliation(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 169 Reconciliation verified successfully: overall_status={result['overall_status']}")
    print(f"All components passed: {result['all_components_passed']}")
    print(
        f"Gross PnL: {result['economics']['gross_pnl_usd']} USD, "
        f"Fees: {result['economics']['total_commissions_usd']} USD, "
        f"Net: {result['economics']['net_pnl_usd']} USD"
    )
    print(
        f"Balance: {result['balance_summary']['pre_experiment_balance_usd']} -> "
        f"{result['balance_summary']['post_experiment_balance_usd']} USD "
        f"(residual {result['balance_summary']['residual_usd']} USD)"
    )
    print(f"Wrote report to {args.output}")
    return 0 if result["all_components_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
