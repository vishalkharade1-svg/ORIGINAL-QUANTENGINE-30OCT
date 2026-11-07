"""Regression: funding-hold settlement targeting must be computed, not
hardcoded to a calendar date.

Defect (found 2026-10-16): `funding_settlement_hold.py` held until
`now.day == 16 and (hour, minute) >= (0, 5)`, i.e. one specific past
instant. Re-run against any later settlement it would have broken out of
the hold loop immediately and exited without capturing funding, while
still reporting success. The hold must instead resolve the settlement it
is targeting (next 00/08/16 UTC boundary, or an explicit instant).
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "funding_settlement_hold.py"


def _load():
    spec = importlib.util.spec_from_file_location("funding_hold_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TestSettlementTargeting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_next_boundary_before_sixteen(self):
        # 15:31 -> the 16:00 boundary is 29 minutes ahead: eligible.
        self.assertEqual(self.m.target_settlement(None, now=_utc(2026, 10, 16, 15, 31)),
                         _utc(2026, 10, 16, 16, 0))

    def test_boundary_ten_minutes_ahead_is_eligible(self):
        self.assertEqual(self.m.target_settlement(None, now=_utc(2026, 10, 16, 15, 50)),
                         _utc(2026, 10, 16, 16, 0))

    def test_too_close_boundary_rolls_to_next_day(self):
        # 15:51 -> 16:00 is only 9 minutes ahead: not enough entry time.
        self.assertEqual(self.m.target_settlement(None, now=_utc(2026, 10, 16, 15, 51)),
                         _utc(2026, 10, 17, 0, 0))

    def test_midnight_and_wrap(self):
        self.assertEqual(self.m.target_settlement(None, now=_utc(2026, 10, 16, 0, 5)),
                         _utc(2026, 10, 16, 8, 0))
        self.assertEqual(self.m.target_settlement(None, now=_utc(2026, 10, 16, 23, 30)),
                         _utc(2026, 10, 17, 0, 0))

    def test_explicit_instant_z_suffix(self):
        self.assertEqual(self.m.target_settlement("2026-10-16T16:00:00Z"),
                         _utc(2026, 10, 16, 16, 0))

    def test_explicit_naive_instant_is_utc(self):
        self.assertEqual(self.m.target_settlement("2026-10-16T16:00:00"),
                         _utc(2026, 10, 16, 16, 0))

    def test_explicit_offset_is_normalised(self):
        self.assertEqual(self.m.target_settlement("2026-10-16T21:30:00+05:30"),
                         _utc(2026, 10, 16, 16, 0))

    def test_hold_loop_is_settlement_driven(self):
        """The defect pin: the hold must not test a hardcoded calendar date."""
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("now.day ==", src,
                         "hold loop must not branch on a hardcoded calendar day")
        self.assertIn("target_settlement(args.settlement)", src)
        self.assertIn("hold_deadline", src)

    def test_hold_deadline_is_settlement_plus_margin(self):
        settle = self.m.target_settlement(None, now=_utc(2026, 10, 16, 15, 31))
        self.assertEqual(settle + timedelta(minutes=5), _utc(2026, 10, 16, 16, 5))


if __name__ == "__main__":
    unittest.main()
