"""Local reconciliation + credential-redaction contract tests.

Provenance: LOCAL CONTRACT TEST — deterministic simulations against
fake executors, NOT exchange evidence.  They pin fail-closed behavior
of the journal/startup/runtime seams that must hold regardless of
which venue (if any) is eventually wired.

Stdlib only. No network, no clock, no credentials.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def positions_feed(records=None, error=None):
    def fetch():
        if error is not None:
            raise error
        return records
    return SimpleNamespace(positions=fetch)


def mirror(*, side="LONG", quantity=2.0, entry=100.0):
    return {"side": side, "quantity": quantity, "entry": entry}


class TestStaleSnapshotPin(unittest.TestCase):
    def test_local_state_without_journal_halts(self):
        import tempfile
        from core.live.reconciler import Reconciler

        with tempfile.TemporaryDirectory() as tmp:
            rec = Reconciler(
                executor=positions_feed([]),
                snapshot_path=tmp + "/missing.json",
            )
            out = rec.startup_check(dry_run=False, local_in_position=True)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "STALE_SNAPSHOT")


class TestDuplicateCheckIdempotent(unittest.TestCase):
    def test_repeated_divergent_checks_stay_halted(self):
        from core.live.reconciler import Reconciler

        rec = Reconciler(executor=positions_feed([]))
        local = mirror()
        first = rec.runtime_check(1, 100, local, None)
        second = rec.runtime_check(2, 200, local, None)
        self.assertEqual(first["verdict"], "MISMATCH")
        self.assertEqual(second["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)

    def test_repeated_matching_checks_stay_quiet(self):
        from core.live.reconciler import Reconciler

        feed = [mirror()]
        rec = Reconciler(executor=positions_feed(feed))
        for bar in (1, 2, 3):
            out = rec.runtime_check(bar, 100 + bar, mirror(), None)
            self.assertEqual(out["verdict"], "MATCH")
        self.assertFalse(rec.halt_new_orders)
        self.assertEqual(rec.drifts, [])


class TestOpenOrdersSeamLocal(unittest.TestCase):
    def test_open_orders_parsing_is_tolerant(self):
        from core.live.reconciler import Reconciler

        rec = Reconciler(executor=None)
        self.assertEqual(rec._exchange_open_orders(), None)
        rec2 = Reconciler(
            executor=SimpleNamespace(
                open_orders=lambda: {"result": [{"id": "O-1"}]}))
        self.assertEqual(rec2._exchange_open_orders(), [{"id": "O-1"}])
        rec3 = Reconciler(executor=SimpleNamespace(open_orders=lambda: None))
        self.assertEqual(rec3._exchange_open_orders(), [])

    def test_open_orders_feed_is_unwired_to_verdicts(self):
        # LOCAL documentation: no core verdict path consumes the open-
        # orders feed, so remote-order reconciliation is UNVERIFIED.
        # This pin fails loudly if anyone wires it without updating
        # the reconciliation contract and drills.
        hits = []
        for path in (ROOT / "core").rglob("*.py"):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                code = line.split("#", 1)[0]
                if "_exchange_open_orders" not in code:
                    continue
                if "def _exchange_open_orders" in code:
                    continue
                hits.append("%s:%d" % (path.relative_to(ROOT), number))
        self.assertEqual(hits, [])


class TestCredentialRedaction(unittest.TestCase):
    def test_banner_never_carries_secret_values(self):
        from core.execution.live_safety_gate import (
            ExecutionMode, LiveSafetyGate)

        marker_key = "PHASE5-MARKER-KEY-VALUE"
        marker_secret = "PHASE5-MARKER-SECRET-VALUE"
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE, allow_live=True, live_execute=True,
            api_key=marker_key, api_secret=marker_secret)
        self.assertTrue(decision.allowed)
        blob = "\n".join(LiveSafetyGate.format_banner(decision))
        blob += "\n" + str(LiveSafetyGate.describe(decision))
        self.assertNotIn(marker_key, blob)
        self.assertNotIn(marker_secret, blob)


if __name__ == "__main__":
    unittest.main()
