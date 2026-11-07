"""Phase-13 P1: reconciliation adversarial LOCAL coverage.

Every case runs against fake executors (LOCAL_VERIFIED only — never
EXCHANGE_VERIFIED; no network, no invented fills):

  missing / unexpected / duplicate remote positions; conflicting
  snapshots; partial fills; quantity mismatch; stale snapshots;
  unknown order status; restart re-derivation; repeated-check
  idempotency; halt persistence semantics; operator resolution.

Deterministic, offline, stdlib only.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace


def reconciler(positions, **kwargs):
    from core.live.reconciler import Reconciler

    return Reconciler(executor=SimpleNamespace(positions=positions),
                      **kwargs)


def local(side="LONG", quantity=2.0, entry=100.0):
    return {"side": side, "quantity": quantity, "entry": entry}


def remote(side="LONG", quantity=2.0, entry=100.0):
    return {"side": side, "quantity": quantity, "entry": entry}


class TestReconciliationAdversarial(unittest.TestCase):
    def test_match_when_mirrored(self):
        rec = reconciler(lambda: [remote()])
        out = rec.runtime_check(1, 1000, local(), None)
        self.assertEqual(out["verdict"], "MATCH")
        self.assertFalse(rec.halt_new_orders)

    def test_missing_remote_position_halts(self):
        rec = reconciler(lambda: [])
        out = rec.runtime_check(5, 1000, local(), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "MISSING_POSITION")

    def test_unexpected_remote_position_halts(self):
        rec = reconciler(lambda: [remote()])
        out = rec.runtime_check(5, 1000, None, None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "UNEXPECTED_POSITION")

    def test_duplicate_remote_positions_halt(self):
        rec = reconciler(lambda: [remote(), remote()])
        out = rec.runtime_check(5, 1000, local(), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "EXTRA_POSITIONS")

    def test_partial_fill_halts_with_kind(self):
        rec = reconciler(lambda: [remote(quantity=1.0)])
        out = rec.runtime_check(5, 1000, local(quantity=2.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "PARTIAL_FILL_QTY")

    def test_quantity_mismatch_halts(self):
        rec = reconciler(lambda: [remote(quantity=5.0)])
        out = rec.runtime_check(5, 1000, local(quantity=2.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertEqual(rec.drifts[-1]["kind"], "QTY_MISMATCH")

    def test_side_mismatch_halts(self):
        rec = reconciler(lambda: [remote(side="SHORT")])
        out = rec.runtime_check(5, 1000, local(side="LONG"), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertEqual(rec.drifts[-1]["kind"], "SIDE_MISMATCH")

    def test_stale_snapshot_halts_startup(self):
        import tempfile

        from core.live.reconciler import Reconciler

        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/broker_state.json"
            first = Reconciler(executor=None, snapshot_path=path)
            trade = SimpleNamespace(direction="LONG", entry=100.0,
                                    stop_loss=90.0, take_profit=160.0,
                                    quantity=2.0, entry_time=1)
            state = first.snapshot_state(True, None, "BTCUSD", trade,
                                         1000, "ACKNOWLEDGED", 3)
            self.assertTrue(first.persist(state))
            # Exchange flat while the journal says in-position.
            reboot = Reconciler(
                executor=SimpleNamespace(positions=lambda: []),
                snapshot_path=path)
            out = reboot.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MISMATCH")
            self.assertTrue(reboot.halt_new_orders)

    def test_unknown_order_status_no_crash(self):
        # An executor whose feed raises -> UNKNOWN/EXECUTOR_ERROR
        # halt, fail-closed (never a crash, never a pass).
        from core.live.reconciler import Reconciler

        def boom():
            raise ConnectionError("feed down")

        rec = Reconciler(executor=SimpleNamespace(positions=boom))
        out = rec.runtime_check(5, 1000, local(), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "EXECUTOR_ERROR")

    def test_restart_rederives_halt(self):
        # Halt state is NOT persisted: a reboot with a flat journal
        # and a flat exchange resumes clean; with divergence it
        # re-halts from evidence, not from memory.
        import tempfile

        from core.live.reconciler import Reconciler

        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/broker_state.json"
            flat = Reconciler(executor=None, snapshot_path=path)
            self.assertTrue(flat.persist(flat.snapshot_state(
                False, None, "BTCUSD", None, 2000, None, 4)))
            back = Reconciler(
                executor=SimpleNamespace(positions=lambda: []),
                snapshot_path=path)
            out = back.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MATCH")
            self.assertFalse(back.halt_new_orders)

    def test_repeated_checks_idempotent(self):
        # Repeated identical divergences re-halt deterministically;
        # repeated matches never latch.
        rec = reconciler(lambda: [])
        for bar in range(1, 6):
            out = rec.runtime_check(bar, 1000 + bar, local(), None)
            self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        rec2 = reconciler(lambda: [remote()])
        for bar in range(1, 6):
            out = rec2.runtime_check(bar, 1000 + bar, local(), None)
            self.assertEqual(out["verdict"], "MATCH")
        self.assertFalse(rec2.halt_new_orders)
        self.assertEqual(rec2.checks_run, 5)

    def test_halt_requires_operator_resolution(self):
        rec = reconciler(lambda: [])
        rec.runtime_check(5, 1000, local(), None)
        self.assertTrue(rec.halt_new_orders)
        with self.assertRaises(ValueError):
            rec.resolve("")
        self.assertTrue(rec.halt_new_orders)
        self.assertTrue(rec.resolve("operator verified flat"))
        self.assertFalse(rec.halt_new_orders)

    def test_in_flight_transient_not_halt(self):
        # A freshly routed order (transit state, young age) with no
        # exchange position yet is IN_FLIGHT, not a divergence.
        rec = reconciler(lambda: [])
        order = {"status": "NEW", "age_bars": 2}
        out = rec.runtime_check(5, 1000, None, order)
        self.assertEqual(out["verdict"], "IN_FLIGHT")
        self.assertFalse(rec.halt_new_orders)
        # An aged transit order with nothing on exchange is lost.
        old = {"status": "NEW", "age_bars": 9999}
        out2 = rec.runtime_check(5, 1000, None, old)
        self.assertEqual(out2["verdict"], "MISMATCH")

    def test_paper_mode_skips_without_authority(self):
        from core.live.reconciler import Reconciler

        rec = Reconciler(executor=None)
        out = rec.startup_check(dry_run=True)
        self.assertEqual(out["verdict"], "SKIP")


if __name__ == "__main__":
    unittest.main()
