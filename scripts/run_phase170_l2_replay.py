"""Runner script for Phase 170 L2 Execution Replay Simulation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.research.l2_execution_replay import run_offline_l2_replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        default=REPO_ROOT / "research" / "captures" / "phase167_recon" / "l2" / "delta_ob_updates_archive.json",
        help="Path to delta_ob_updates_archive.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "research" / "results" / "phase170_l2_execution_replay.json",
        help="Path to save simulation results",
    )
    args = parser.parse_args()

    print(f"Running offline L2 execution replay against {args.archive}...")
    res = run_offline_l2_replay(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Replay complete across {res['total_archive_frames']} frames.")
    for size_key, data in res["replay_results"].items():
        evals = data["evaluations"]
        first_eval = evals[0]["buy_execution"]
        print(f"  Size {size_key}: status={first_eval['status']}, VWAP={first_eval['vwap']}, slippage={first_eval['slippage_bps']} bps, levels={first_eval['levels_consumed']}")
    print(f"Saved results to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
