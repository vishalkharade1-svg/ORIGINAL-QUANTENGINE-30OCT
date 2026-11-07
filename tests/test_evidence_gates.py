"""Evidence-gate dependency graph: machine-checkable acceptance tests.

Hermetic, stdlib-only. Proves the corrected prerequisite and
independence model (core/evidence/gates.py):

* hard prerequisites propagate BLOCKED_BY_PREREQUISITE only where a
  genuine information dependency exists;
* independent gates (paper, isolation, secrets, determinism,
  research, artifact validity) stay executable when G2 is blocked;
* reconciliation is field-level (one missing domain does not erase
  another verified domain);
* blocked evidence still yields a valid artifact/matrix;
* no gate can enable production execution;
* matrices are deterministic.
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from core.evidence.gates import (
    DEFINITIONS,
    GATE_IDS,
    GateError,
    GateMatrix,
    GateResult,
    external_final,
    lifecycle_attempt_allowed,
    validate_matrix,
)


def _res(gate_id, status="VERIFIED", execution="EXECUTED", **over):
    params = {
        "gate_id": gate_id,
        "status": status,
        "execution_state": execution,
        "prerequisites": (),
        "satisfied_prerequisites": (),
        "missing_prerequisites": (),
        "required_evidence": (),
        "observed_evidence": (),
        "missing_evidence": (),
        "blocking_reasons": (),
        "limitations": (),
    }
    params.update(over)
    return GateResult(**params)


def _baseline(**over):
    """Full G0-G14 result set for the current real-world state.

    G2 BLOCKED (no sandbox credentials); dependents blocked;
    independent gates verified; research unevaluated.
    """
    results = {
        "G0": _res("G0"),
        "G1": _res("G1"),
        "G2": _res("G2", status="BLOCKED", execution="EXECUTED",
                   observed_evidence=("config_checked", "refusal_observed"),
                   missing_evidence=("authenticated_response",),
                   blocking_reasons=("CONFIGURATION_MISSING",)),
        "G3": _res("G3", status="BLOCKED",
                   execution="BLOCKED_BY_PREREQUISITE",
                   prerequisites=("G2",), missing_prerequisites=("G2",),
                   missing_evidence=("account_read",),
                   blocking_reasons=("prerequisite G2 unavailable",)),
        "G4": _res("G4", status="BLOCKED", execution="EXECUTED",
                   observed_evidence=("public_source_available",),
                   missing_evidence=("contract_observation",),
                   blocking_reasons=("no contract observation performed",)),
        "G5": _res("G5", status="BLOCKED",
                   execution="BLOCKED_BY_PREREQUISITE",
                   prerequisites=("G4",), missing_prerequisites=("G4",),
                   missing_evidence=("economics_observation",),
                   blocking_reasons=("prerequisite G4 unavailable",)),
        "G6": _res("G6", status="BLOCKED",
                   execution="BLOCKED_BY_PREREQUISITE",
                   prerequisites=("G2", "G3", "G4"),
                   missing_prerequisites=("G2", "G3", "G4"),
                   missing_evidence=("lifecycle_observation",),
                   blocking_reasons=("prerequisites unavailable",
                                     "no order attempted",)),
        "G7": _res("G7", status="BLOCKED", execution="EXECUTED",
                   observed_evidence=("account=NO_SOURCE",
                                      "contract=NO_SOURCE",
                                      "economics=NO_SOURCE",
                                      "lifecycle=NO_SOURCE"),
                   missing_evidence=("source_evidence",),
                   blocking_reasons=("nothing to compare",)),
        "G8": _res("G8"),
        "G9": _res("G9"),
        "G10": _res("G10"),
        "G11": _res("G11"),
        "G12": _res("G12"),
        "G13": _res("G13", status="BLOCKED", execution="NOT_ATTEMPTED",
                    missing_evidence=("research_evaluation",),
                    blocking_reasons=("not evaluated in this run",)),
        "G14": _res("G14"),
    }
    results.update(over)
    return [results[g] for g in GATE_IDS]


def _matrix(**over):
    return GateMatrix.create(_baseline(**over))


class TestDefinitions(unittest.TestCase):
    def test_all_gates_defined_once(self):
        self.assertEqual(tuple(DEFINITIONS), GATE_IDS)
        self.assertEqual(len(DEFINITIONS), 15)

    def test_conditional_edges_explicit(self):
        g4 = DEFINITIONS["G4"]
        self.assertTrue(any(p.gate_id == "G2" and "authenticated" in p.condition
                            for p in g4.prerequisites))
        g6 = DEFINITIONS["G6"]
        self.assertEqual({p.gate_id for p in g6.prerequisites},
                         {"G2", "G3", "G4"})

    def test_independent_gates_have_no_prerequisites(self):
        for gate_id in ("G0", "G1", "G8", "G10", "G11", "G12",
                        "G13", "G14"):
            self.assertEqual(DEFINITIONS[gate_id].prerequisites, (),
                             gate_id)


class TestPrerequisiteBehavior(unittest.TestCase):
    def test_g2_failure_blocks_g3(self):
        mat = _matrix()
        g3 = [r for r in mat.results if r.gate_id == "G3"][0]
        self.assertEqual(g3.status, "BLOCKED")
        self.assertEqual(g3.execution_state, "BLOCKED_BY_PREREQUISITE")
        self.assertIn("G2", g3.missing_prerequisites)

    def test_g3_verified_without_g2_rejected(self):
        with self.assertRaises(GateError):
            _matrix(G3=_res("G3", observed_evidence=("account_read",)))

    def test_g4_authenticated_claim_without_g2_rejected(self):
        with self.assertRaises(GateError):
            _matrix(G4=_res("G4", observed_evidence=(
                "public_source_available", "authenticated_source")))

    def test_g4_public_blocked_without_g2_allowed(self):
        mat = _matrix()  # G4 BLOCKED/EXECUTED, no auth claimed: valid
        g4 = [r for r in mat.results if r.gate_id == "G4"][0]
        self.assertEqual(g4.execution_state, "EXECUTED")

    def test_g5_contract_claim_without_g4_rejected(self):
        with self.assertRaises(GateError):
            _matrix(G5=_res("G5", status="PARTIAL",
                            observed_evidence=(
                                "contract_identity_required",
                                "maker_fee",)))

    def test_g6_attempt_requires_triple(self):
        with self.assertRaises(GateError):
            _matrix(G6=_res("G6", status="PARTIAL",
                            observed_evidence=("submission_accepted",)))
        self.assertFalse(lifecycle_attempt_allowed(
            {r.gate_id: r for r in _baseline()}))

    def test_g7_contract_without_account(self):
        mat = _matrix(G7=_res(
            "G7", status="PARTIAL", execution="EXECUTED",
            observed_evidence=("account=NO_SOURCE",
                               "contract=VERIFIED",
                               "economics=NO_SOURCE",
                               "lifecycle=NOT_ATTEMPTED"),
            missing_evidence=("account_source", "economics_source"),
            limitations=("contract reconciled without account",)))
        g7 = [r for r in mat.results if r.gate_id == "G7"][0]
        self.assertEqual(g7.status, "PARTIAL")

    def test_g7_account_without_economics(self):
        mat = _matrix(G7=_res(
            "G7", status="PARTIAL", execution="EXECUTED",
            observed_evidence=("account=VERIFIED",
                               "contract=NO_SOURCE",
                               "economics=NO_SOURCE",
                               "lifecycle=NOT_ATTEMPTED"),
            missing_evidence=("contract_source", "economics_source"),
            limitations=("account reconciled without economics",)))
        self.assertEqual(
            [r for r in mat.results if r.gate_id == "G7"][0].status,
            "PARTIAL")

    def test_g7_verified_with_mismatch_rejected(self):
        with self.assertRaises(GateError):
            _matrix(G7=_res("G7", observed_evidence=(
                "account=VERIFIED", "contract=MISMATCH")))


class TestIndependence(unittest.TestCase):
    def _independent_ok(self, gate_id):
        mat = _matrix()
        res = [r for r in mat.results if r.gate_id == gate_id][0]
        self.assertEqual(res.status, "VERIFIED")
        self.assertEqual(res.execution_state, "EXECUTED")

    def test_g2_blocked_does_not_block_g8(self):
        self._independent_ok("G8")

    def test_g2_blocked_does_not_block_g10(self):
        self._independent_ok("G10")

    def test_g2_blocked_does_not_block_g11(self):
        self._independent_ok("G11")

    def test_g2_blocked_does_not_block_g12(self):
        self._independent_ok("G12")

    def test_g2_blocked_does_not_block_g14(self):
        self._independent_ok("G14")

    def test_g13_unevaluated_not_failed(self):
        mat = _matrix()
        g13 = [r for r in mat.results if r.gate_id == "G13"][0]
        self.assertEqual(g13.execution_state, "NOT_ATTEMPTED")
        self.assertNotEqual(g13.status, "VERIFIED")


class TestArtifactBehavior(unittest.TestCase):
    def test_blocked_evidence_valid_matrix(self):
        mat = _matrix()
        self.assertEqual(mat.external_classification,
                         "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")

    def test_partial_evidence_valid_matrix(self):
        mat = _matrix(
            G2=_res("G2", observed_evidence=("authenticated_response",)),
            G3=_res("G3", observed_evidence=("account_read",)),
            G4=_res("G4", observed_evidence=("contract_observation",)),
            G5=_res("G5", status="PARTIAL", execution="EXECUTED",
                    observed_evidence=("maker_fee",),
                    missing_evidence=("funding_mechanism",),
                    limitations=("funding unavailable",)),
            G6=_res("G6", status="NOT_ATTEMPTED", execution="NOT_ATTEMPTED",
                    prerequisites=("G2", "G3", "G4"),
                    satisfied_prerequisites=("G2", "G3", "G4"),
                    missing_evidence=("lifecycle_observation",),
                    blocking_reasons=("lifecycle not required",)),
            G7=_res("G7", status="PARTIAL", execution="EXECUTED",
                    observed_evidence=("account=VERIFIED",
                                       "contract=VERIFIED",
                                       "economics=BLOCKED",
                                       "lifecycle=NOT_ATTEMPTED"),
                    missing_evidence=("economics_source",),
                    limitations=("economics unavailable",)),
        )
        self.assertEqual(mat.external_classification,
                         "SANDBOX_EXTERNAL_EVIDENCE_PARTIAL")

    def test_verified_evidence_valid_matrix(self):
        verified_external = {
            gid: _res(gid, observed_evidence=("observed",))
            for gid in ("G2", "G3", "G4", "G5", "G6")
        }
        verified_external["G7"] = _res(
            "G7", observed_evidence=("account=VERIFIED",
                                     "contract=VERIFIED",
                                     "economics=VERIFIED",
                                     "lifecycle=VERIFIED"))
        mat = _matrix(**verified_external)
        self.assertEqual(mat.external_classification,
                         "SANDBOX_EXTERNAL_EVIDENCE_VERIFIED")

    def test_invalid_result_rejected(self):
        with self.assertRaises(GateError):
            _res("G0", missing_evidence=("head",),
                 blocking_reasons=("missing",))

    def test_deterministic_matrix(self):
        first, second = _matrix(), _matrix()
        self.assertEqual(first.matrix_id, second.matrix_id)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))

    def test_g13_executed_blocked_with_suite_pins(self):
        # Mirrors the live runner: 9M suites executed, blocked only
        # by pre-existing digest pins (no verdict suppressed).
        mat = _matrix(G13=_res(
            "G13", status="BLOCKED", execution="EXECUTED",
            observed_evidence=("oos_suites=92/failed=5",),
            missing_evidence=("all_suite_failures_resolved",),
            limitations=("digest pins pre-existing/forensic",)))
        g13 = [r for r in mat.results if r.gate_id == "G13"][0]
        self.assertEqual(g13.status, "BLOCKED")
        self.assertEqual(g13.execution_state, "EXECUTED")
        self.assertEqual(mat.external_classification,
                         "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")

    def test_changed_verdict_changed_id(self):
        self.assertNotEqual(
            _matrix().matrix_id,
            _matrix(G8=_res("G8", status="PARTIAL", execution="EXECUTED",
                            missing_evidence=("observations",),
                            limitations=("counters unavailable",))).matrix_id)


class TestSafety(unittest.TestCase):
    def test_blocked_prereq_means_no_lifecycle_attempt(self):
        by_id = {r.gate_id: r for r in _baseline()}
        self.assertFalse(lifecycle_attempt_allowed(by_id))
        g6 = by_id["G6"]
        self.assertNotIn("submission_accepted", g6.observed_evidence)
        self.assertIn("no order attempted", g6.blocking_reasons)

    def test_production_ready_cannot_be_true(self):
        mat = _matrix()
        self.assertIs(mat.is_production_ready, False)
        self.assertIs(mat.to_dict()["is_production_ready"], False)
        with self.assertRaises(GateError):
            dataclasses.replace(mat, is_production_ready=True)

    def test_no_transitive_global_failure(self):
        mat = _matrix()
        by_id = {r.gate_id: r for r in mat.results}
        # G2 BLOCKED, yet independent gates stay VERIFIED.
        self.assertEqual(by_id["G2"].status, "BLOCKED")
        for gate_id in ("G8", "G10", "G11", "G12", "G14"):
            self.assertEqual(by_id[gate_id].status, "VERIFIED",
                             gate_id)

    def test_external_final_helper(self):
        by_id = {r.gate_id: r for r in _baseline()}
        self.assertEqual(external_final(by_id),
                         "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")

    def test_matrix_order_enforced(self):
        with self.assertRaises(GateError):
            GateMatrix.create(list(reversed(_baseline())))

    def test_validate_matrix_rejects_missing_gate(self):
        with self.assertRaises(GateError):
            validate_matrix({r.gate_id: r for r in _baseline()[:-1]})


if __name__ == "__main__":
    unittest.main()
