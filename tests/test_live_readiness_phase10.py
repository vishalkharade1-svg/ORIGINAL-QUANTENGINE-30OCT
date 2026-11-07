"""Local tests cannot silently certify operator/exchange evidence."""

import unittest

from core.live.readiness import LiveReadinessEvidence, assess_live_readiness


class TestLiveReadiness(unittest.TestCase):
    def test_default_is_not_live_ready_and_names_all_gates(self):
        decision = assess_live_readiness(LiveReadinessEvidence())
        self.assertFalse(decision.ready)
        self.assertEqual(decision.status, "NOT_LIVE_READY")
        self.assertIn("SANDBOX_ORDER_LIFECYCLE", decision.missing)
        self.assertIn("CREDENTIAL_ROTATION_AND_HISTORY_REMEDIATION", decision.missing)

    def test_only_complete_explicit_evidence_reaches_canary_review(self):
        evidence = LiveReadinessEvidence(
            credentials_rotated_and_history_remediated=True,
            public_data_contract_verified=True,
            contract_and_cost_semantics_verified=True,
            sandbox_order_lifecycle_verified=True,
            reconciliation_restart_drill_verified=True,
            paper_soak_with_realistic_costs_verified=True,
            independent_monitoring_and_rollback_verified=True,
        )
        decision = assess_live_readiness(evidence)
        self.assertTrue(decision.ready)
        self.assertEqual(decision.status, "READY_FOR_CANARY_REVIEW")
        self.assertEqual(decision.missing, ())


if __name__ == "__main__":
    unittest.main()
