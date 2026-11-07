"""Evidence closure matrix tests (deterministic, offline, stdlib only).

Pins the matrix's determinism, schema, closed vocabulary, and honest
statuses: no row may claim venue verification, and every blocked row
must name its closure condition, action, and reason.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evidence_closure_matrix.py"

STATUSES = (
    "VERIFIED", "PARTIAL", "LOCAL_VERIFIED", "UNVERIFIED",
    "NOT_OBSERVED", "BLOCKED", "UNWIRED", "OPERATOR_CONTROLLED",
)

READINESS = (
    "CODE_READY", "TEST_READY", "EVIDENCE_READY",
    "EVIDENCE_AVAILABLE", "EVIDENCE_VERIFIED", "EVIDENCE_UNAVAILABLE",
)

FIELDS = (
    "blocker_id", "capability", "claim", "evidence_required",
    "evidence_currently_available", "evidence_type",
    "authoritative_source_required", "repository_capture_mechanism",
    "parser_support_status", "test_status", "external_dependency",
    "closure_condition", "current_status", "code_readiness",
    "test_readiness", "evidence_readiness", "owner_action_required",
    "reason_blocked",
)

VAGUE = ("almost done", "nearly ready", "probably ready")


def load_matrix() -> list[dict]:
    out = subprocess.run(
        ["python", str(SCRIPT), "--json"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


class TestClosureMatrix(unittest.TestCase):
    def test_output_deterministic(self):
        first = load_matrix()
        second = load_matrix()
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, indent=2, sort_keys=True),
            json.dumps(second, indent=2, sort_keys=True),
        )

    def test_schema_exact_and_ordered(self):
        matrix = load_matrix()
        self.assertGreaterEqual(len(matrix), 15)
        ids = [row["blocker_id"] for row in matrix]
        self.assertEqual(len(ids), len(set(ids)))
        for row in matrix:
            self.assertEqual(tuple(sorted(row.keys())), tuple(sorted(FIELDS)))

    def test_closed_vocabulary_only(self):
        matrix = load_matrix()
        for row in matrix:
            with self.subTest(blocker=row["blocker_id"]):
                self.assertIn(row["current_status"], STATUSES)
                self.assertIn(row["code_readiness"], READINESS)
                self.assertIn(row["test_readiness"], READINESS)
                self.assertIn(row["evidence_readiness"], READINESS)
                blob = json.dumps(row).lower()
                for vague in VAGUE:
                    self.assertNotIn(vague, blob)

    def test_no_venue_verification_claimed(self):
        matrix = load_matrix()
        for row in matrix:
            with self.subTest(blocker=row["blocker_id"]):
                self.assertNotIn(
                    row["current_status"],
                    ("VERIFIED", "PARTIAL", "LOCAL_VERIFIED"),
                    "venue claim must not be marked verified",
                )
                self.assertEqual(row["evidence_readiness"],
                                 "EVIDENCE_UNAVAILABLE")

    def test_every_blocker_actionable(self):
        matrix = load_matrix()
        for row in matrix:
            with self.subTest(blocker=row["blocker_id"]):
                for field in ("closure_condition", "owner_action_required",
                              "reason_blocked", "evidence_required"):
                    self.assertTrue(row[field].strip(), field)

    def test_expected_blockers_present(self):
        ids = {row["blocker_id"] for row in load_matrix()}
        for expected in (
            "global-rollover", "server-recovery", "candle-finality",
            "sequence-semantics", "contract-tick-size",
            "contract-multiplier", "contract-qty-step", "contract-min-qty",
            "contract-settlement-margin", "economics-fees",
            "economics-slippage", "economics-gates", "private-orders",
            "private-fills", "private-positions", "private-balances",
            "private-cancellations", "private-restart",
            "reconciliation-venue", "digest-recert",
            "credential-rotation",
        ):
            self.assertIn(expected, ids)


if __name__ == "__main__":
    unittest.main()
