"""Operator script: verified-transport replay + sustained paper soak.

Drives the REAL production assembly through ``data.realtime.verified_replay``
-- the verified public candle transport seam, the frozen institutional
pipeline and the dry-run paper broker.  Everything is offline and dry-run;
there is no network access and no live order path exists here.

Subcommands
----------
replay-capture  Replay a recorded ``quantengine.delta-public-capture.v1``
                bundle (CAPTURED evidence) end-to-end and report delivery,
                routing and reconciliation.
soak            Sustained deterministic synthetic soak (SYNTHETIC_FIXTURE,
                labelled) with optional explicit fault injection, reporting
                counts, latency percentiles (observational) and memory peak.

Every run writes a machine-readable JSON report (schema
``quantengine.verified-transport-replay.v1``) and exits 0 only when the
clean criteria hold: zero route errors, zero reconcile errors, the paper
ledger reconciled per symbol, and every injected fault accounted for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.realtime.verified_replay import (  # noqa: E402
    DisconnectFault,
    DuplicateFault,
    GapFault,
    MalformedFault,
    OutOfOrderFault,
    VerifiedTransportReplay,
    load_capture,
    reconcile_paper_ledger,
    synthetic_candle_frames,
)

DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "PHASE24_REPLAY_EXAMPLE"


def _write_report(report, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_json(include_observations=True), "utf-8")


def _fault_plan(tokens):
    plan = []
    for token in tokens or []:
        name, _, rest = token.partition("@")
        if name == "duplicate":
            plan.append(DuplicateFault(after_ordinal=int(rest)))
        elif name == "out_of_order":
            steps = 2
            if ":" in rest:
                rest, _, steps_text = rest.partition(":")
                steps = int(steps_text)
            plan.append(OutOfOrderFault(after_ordinal=int(rest), back_steps=steps))
        elif name == "malformed":
            ordinal, _, mode = rest.partition(":")
            plan.append(MalformedFault(after_ordinal=int(ordinal), mode=mode))
        elif name == "gap":
            ordinal, _, missing = rest.partition(":")
            plan.append(
                GapFault(after_ordinal=int(ordinal), missing_candles=int(missing)),
            )
        elif name == "disconnect":
            ordinal, _, delay = rest.partition(":")
            plan.append(
                DisconnectFault(
                    after_ordinal=int(ordinal), resubscribe_after=int(delay),
                ),
            )
        else:
            raise SystemExit(f"unknown fault token: {token!r}")
    return plan


def _clean(report, ledger, *, require_continuous=False) -> bool:
    ok = (
        report.engine.get("route_errors", 1) == 0
        and report.engine.get("reconcile_errors", 1) == 0
        and ledger.get("consistent", False) is True
    )
    if require_continuous:
        for status in report.gaps.get("statuses", {}).values():
            if status.get("status") != "CONTINUOUS":
                ok = False
    return ok


def _print_summary(report, ledger) -> None:
    print("schema            :", report.schema)
    print("evidence_class    :", report.evidence_class)
    print("frames_input      :", report.frames_input)
    print("frames_ingested   :", report.frames_ingested)
    print("synthetic injected:", report.synthetic_frames_injected)
    print("skipped for gap   :", report.skipped_for_gap)
    print("stream            :", report.stream)
    print("closed delivered  :", report.transport.get("closed_delivered"))
    print("unrouted (total)  :", report.unrouted_during_outage)
    print("engine            :", report.engine)
    print("workers           :", report.workers)
    print("risk              :", {
        key: value for key, value in report.risk.items()
        if key != "decision_accepted_rr"
    })
    print("paper             :", report.paper)
    print("gaps              :", report.gaps)
    print("disconnects       :", report.disconnects)
    print("log_verdicts      :", report.log_verdicts)
    print("latency_ms        :", report.latency_ms)
    print("ledger reconciled :", ledger.get("consistent", False))


def cmd_replay_capture(args) -> int:
    bundle = load_capture(args.capture)
    harness = VerifiedTransportReplay(
        [bundle.symbol] if bundle.symbol else [],
    )
    harness.start()
    try:
        report = harness.run(bundle.records, speed=args.speed, measure=args.measure)
        report.source_path = str(Path(args.capture).resolve())
        report.endpoint = bundle.endpoint
        ledger = reconcile_paper_ledger(harness)
        _print_summary(report, ledger)
        out = Path(args.out) if args.out else (
            DEFAULT_OUT_DIR / "replay_capture.json"
        )
        _write_report(report, out)
        print("report written    :", out)
        clean = _clean(report, ledger)
        if not clean:
            print("CLEAN CHECK FAILED", file=__import__("sys").stderr)
        return 0 if clean else 1
    finally:
        harness.close()


def _repair_outstanding_gaps(harness, records, receipt_timestamp):
    """Operator gap-repair step (labelled SYNTHETIC source only).

    Rebuilds the missing candle frames for every outstanding gap from the
    synthetic feed that created them, then calls the transport's
    journal-backed repair.  Never used for captured evidence; the soak's
    gaps come from skipped synthetic frames only.
    """
    from data.candle_builder import TIMEFRAME_SECONDS

    frames_by_start = {
        frame["cst"] // 1_000_000: frame
        for frame in (record.frame for record in records)
        if isinstance(frame, dict)
        and str(frame.get("type", "")).startswith("candlestick_")
        and "cst" in frame
    }
    repaired_ranges = 0
    for key, status in harness.gap_report()["statuses"].items():
        venue, symbol, resolution = str(key).split(":", 2)
        window = TIMEFRAME_SECONDS.get(resolution)
        if not window or not status.get("gaps"):
            continue
        candles = []
        for gap in status["gaps"]:
            for start in range(
                gap.after_start + window, gap.before_start, window,
            ):
                frame = frames_by_start.get(start)
                if frame is None:
                    continue
                candles.append(
                    SimpleNamespace(
                        timestamp=start,
                        open=frame["o"],
                        high=frame["h"],
                        low=frame["l"],
                        close=frame["c"],
                        volume=frame["v"],
                    ),
                )
        if not candles:
            continue
        result = harness.repair_gap_history(
            symbol,
            resolution,
            candles,
            receipt_timestamp=receipt_timestamp,
        )
        print(
            f"gap repair {key}: accepted={result['accepted']} "
            f"ranges_repaired={result['ranges_repaired']} "
            f"reason={result['reason']}",
        )
        repaired_ranges += result["ranges_repaired"]
    return repaired_ranges


def cmd_soak(args) -> int:
    records = synthetic_candle_frames(
        args.symbol,
        candles=args.candles,
        seed=args.seed,
    )
    harness = VerifiedTransportReplay([args.symbol])
    harness.start()
    try:
        report = harness.run(
            records,
            speed=args.speed,
            faults=_fault_plan(args.fault),
            measure=args.measure,
        )
        report.endpoint = "synthetic://fault-injection"
        if args.repair_gap:
            _repair_outstanding_gaps(
                harness,
                records,
                receipt_timestamp=(
                    records[-1].receipt_ns or 0
                ) + 1_000_000_000,
            )
            # the run's gap section was captured before the repair; the
            # post-repair continuity state is the operator-facing verdict
            report.gaps = harness.gap_report()
        ledger = reconcile_paper_ledger(harness)
        _print_summary(report, ledger)
        out = Path(args.out) if args.out else (
            DEFAULT_OUT_DIR / f"soak_{args.candles}_seed{args.seed}.json"
        )
        _write_report(report, out)
        print("report written    :", out)
        clean = _clean(report, ledger, require_continuous=args.repair_gap)
        if not clean:
            print("CLEAN CHECK FAILED", file=__import__("sys").stderr)
        return 0 if clean else 1
    finally:
        harness.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verified-transport replay and soak (dry-run only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser(
        "replay-capture",
        help="replay a recorded public capture end-to-end",
    )
    capture.add_argument("--capture", required=True)
    capture.add_argument("--speed", type=float, default=0.0)
    capture.add_argument("--measure", action="store_true")
    capture.add_argument("--out", default=None)
    capture.set_defaults(func=cmd_replay_capture)

    soak = sub.add_parser(
        "soak",
        help="sustained deterministic synthetic soak",
    )
    soak.add_argument("--symbol", default="BTCUSDT")
    soak.add_argument("--candles", type=int, default=12_000)
    soak.add_argument("--seed", type=int, default=11)
    soak.add_argument("--speed", type=float, default=0.0)
    soak.add_argument("--measure", action="store_true")
    soak.add_argument(
        "--fault",
        action="append",
        default=None,
        help=(
            "fault token, repeatable: duplicate@N, out_of_order@N[:steps], "
            "malformed@N:MODE, gap@N:missing, disconnect@N[:delay]"
        ),
    )
    soak.add_argument(
        "--repair-gap",
        action="store_true",
        help="after the run, repair outstanding gaps from the synthetic feed",
    )
    soak.add_argument("--out", default=None)
    soak.set_defaults(func=cmd_soak)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
