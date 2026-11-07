#!/usr/bin/env python3
"""Phase 25 controlled paper-session runner (operator CLI).

Mode A (default) -- AUTHORITATIVE paper session:
    python scripts/run_paper_session.py --run-seconds 600

    Real public Delta Global REST closed candles (BTCUSDT 1m default)
    through the real engine assembly; simulated fills only; every market
    observation labelled exchange-sourced. Requires network reachability
    to https://api.delta.exchange; fails clearly when the endpoint is
    unreachable (no fixture substitution, no fabricated evidence).

Mode B -- OFFLINE replay (never a live-session claim):
    python scripts/run_paper_session.py --mode replay --synthetic-seed 99
    python scripts/run_paper_session.py --mode replay --capture <bundle>

Safety (fail-closed):
    * Refuses when LIVE execution is armed (LIVE_MODE/EXECUTION_MODE).
    * PAPER-only, dry-run broker; the transport has no order path.
    * Credentials are never required or used (public market data only).

Cost economics: the session REPORTS the resolved paper cost profile.
Venue-realistic costs are UNKNOWN until provisioned by the operator
(PAPER_COMMISSION_PER_TRADE / PAPER_COMMISSION_RATE /
PAPER_SLIPPAGE_BPS + PAPER_COST_VENUE_REALISTIC / PAPER_COST_PROFILE_NAME
set BEFORE launch); the default profile is explicit-zero-neutral.

Artifacts: reports/PAPER_SESSIONS/<session_id>/{session_report.json,
delivered_candles.jsonl, session_summary.md}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Phase 25 controlled paper session")
    parser.add_argument(
        "--mode", choices=("live", "replay"), default="live",
        help="live = authoritative REST data paper session; "
             "replay = offline Phase-24 verified replay (Mode B)")
    parser.add_argument("--symbols", default="BTCUSDT",
                        help="comma list (live mode)")
    parser.add_argument("--timeframe", default="1m",
                        help="1m/5m/15m/1h/4h/1d (live mode)")
    parser.add_argument("--run-seconds", type=float, default=600.0,
                        help="bounded run (live mode); 0 = until Ctrl+C")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=15.0)
    parser.add_argument("--lookback-days", type=int, default=1)
    parser.add_argument("--output-dir", default="reports/PAPER_SESSIONS")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--no-capture", action="store_true",
                        help="skip delivered-candle capture")
    parser.add_argument("--capture", default=None,
                        help="replay mode: Phase-24 capture bundle path")
    parser.add_argument("--synthetic-seed", type=int, default=99)
    parser.add_argument("--synthetic-candles", type=int, default=600)
    parser.add_argument("--fault", action="append", default=[],
                        help="replay mode: fault token, e.g. "
                             "duplicate@120, out_of_order@90, "
                             "malformed@60:drop_volume, gap@40:3, "
                             "disconnect@30:2")
    return parser.parse_args(argv)


def _parse_faults(tokens):
    from data.realtime.verified_replay import (
        DisconnectFault,
        DuplicateFault,
        GapFault,
        MalformedFault,
        OutOfOrderFault,
    )

    plans = []
    for token in tokens or ():
        head, _, rest = token.partition(":")
        kind, _, after = head.partition("@")
        kind = kind.strip().lower()
        after = int(after) if after else 0
        if kind == "duplicate":
            plans.append(DuplicateFault(after_ordinal=after))
        elif kind == "out_of_order":
            steps = int(rest) if rest else 2
            plans.append(OutOfOrderFault(after_ordinal=after,
                                         back_steps=steps))
        elif kind == "malformed":
            mode = rest or "drop_volume"
            plans.append(MalformedFault(after_ordinal=after, mode=mode))
        elif kind == "gap":
            missing = int(rest) if rest else 2
            plans.append(GapFault(after_ordinal=after,
                                  missing_candles=missing))
        elif kind == "disconnect":
            resub = int(rest) if rest else 2
            plans.append(DisconnectFault(after_ordinal=after,
                                         resubscribe_after=resub))
        else:
            raise SystemExit("REFUSED: unknown fault token %r" % token)
    return plans


def main(argv=None) -> int:
    args = _parse_args(argv)

    from data.paper_session.paper_session import (
        refuse_live_execution,
        run_replay_session,
    )

    refuse_live_execution()

    if args.mode == "replay":
        report = run_replay_session(
            capture_path=args.capture,
            synthetic_seed=args.synthetic_seed,
            synthetic_candles=args.synthetic_candles,
            faults=_parse_faults(args.fault),
            output_dir=args.output_dir,
            session_id=args.session_id,
        )
        print(json.dumps({
            "session_id": report["session_id"],
            "mode": report["session_mode"],
            "evidence_class": report["evidence_class"],
            "artifacts": report["artifact_paths"],
        }, indent=2, sort_keys=True))
        return 0

    from data.paper_session.paper_session import PaperSessionRunner

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    runner = PaperSessionRunner(
        symbols,
        timeframe=args.timeframe,
        run_seconds=(args.run_seconds if args.run_seconds > 0 else None),
        heartbeat_seconds=args.heartbeat_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        lookback_days=args.lookback_days,
        output_dir=args.output_dir,
        session_id=args.session_id,
        capture_delivered=not args.no_capture,
    )
    receipt = runner.start()
    print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
    report = runner.run()
    print(json.dumps({
        "session_id": report["session_id"],
        "mode": report["session_mode"],
        "evidence_class": report["evidence_class"],
        "routed": report["engine"]["routed"],
        "unrouted": report["engine"]["unrouted"],
        "reconciled": report["reconciliation"].get("consistent"),
        "artifacts": report.get("artifact_paths", {}),
    }, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
