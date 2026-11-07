"""Open-blocker preservation tests (deterministic, offline).

Each test pins a KNOWN-OPEN blocker so no future change can silently
close, rename, or reroute it without updating the pin AND the evidence.
Statuses: VERIFIED_OPEN unless stated.  Nothing here alters production.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures" / "delta"


class TestPhase7BlockersStillOpen(unittest.TestCase):
    def test_confidence_shadow_closed(self):
        # PHASE-4 CORRECTED (was VERIFIED_OPEN): no MIN_CONFIDENCE
        # shadow remains; analyze() reads the authoritative config
        # minimum (80) per candidate.
        import core.setup.decision_engine as DE
        from config import risk_settings
        from core.setup.decision_engine import DecisionEngine

        self.assertEqual(DE.risk_settings.MIN_CONFIDENCE, 80)
        self.assertFalse(hasattr(DecisionEngine, "MIN_CONFIDENCE"))
        self.assertEqual(risk_settings.MIN_CONFIDENCE, 80)

    def test_risk_reward_naming_corrected(self):
        # PHASE-4 CORRECTED (was VERIFIED_OPEN): distinct names with
        # pinned math; the deprecated alias keeps the notional meaning.
        from core.risk.position_size import PositionSize

        ps = PositionSize(balance=2000.0, risk_percent=0.01, risk_amount=20.0,
                          allocation=500.0, leverage=10.0, entry_price=100.0,
                          stop_price=90.0, stop_distance=10.0, quantity=2.0,
                          position_value=500.0, expected_loss=20.0,
                          target_price=160.0)
        self.assertAlmostEqual(ps.notional_to_risk, 500.0 / 20.0)
        self.assertAlmostEqual(ps.reward_to_risk, 6.0)

    def test_manage_into_has_no_core_callers(self):
        hits = []
        for path in (ROOT / "core").rglob("*.py"):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if "manage_into(" not in line:
                    continue
                if stripped.startswith(("#", "*", '"""', "``")):
                    continue
                if "def manage_into" in line or "``" in line:
                    continue
                hits.append("%s:%d" % (path.relative_to(ROOT), number))
        # VERIFIED_OPEN: live-equity integration pending verified wiring.
        self.assertEqual(hits, [])


class TestCredentialFailClosedDefaults(unittest.TestCase):
    def test_no_literal_credentials_in_settings_source(self):
        source = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if "API_KEY" in code or "API_SECRET" in code:
                self.assertNotRegex(
                    code, r'=\s*["\'][^"\']+["\']',
                    "literal credential at config/settings.py:%d" % number,
                )

    def test_blank_credentials_never_arm_live(self):
        from core.execution.live_safety_gate import ExecutionMode, LiveSafetyGate

        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE, allow_live=True, live_execute=True,
            api_key="", api_secret="",
        )
        self.assertFalse(decision.allowed)
        self.assertIn("credentials missing", decision.reason)

    def test_non_live_modes_never_arm(self):
        from core.execution.live_safety_gate import ExecutionMode, LiveSafetyGate

        for mode in (ExecutionMode.PAPER, ExecutionMode.ANALYZE):
            decision = LiveSafetyGate.decide(
                mode=mode, allow_live=True, live_execute=True,
                api_key="k", api_secret="s",
            )
            self.assertFalse(decision.allowed)


class TestServerDisconnectDistinction(unittest.TestCase):
    def test_reconnect_fixtures_state_client_initiated(self):
        for name in (
            "observed_india_btcusd_client_reconnect_20260916.json",
            "observed_global_btcusdt_client_reconnect_20260918.json",
        ):
            bundle = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
            self.assertIn("client-initiated", bundle["limitations"][0])

    def test_verifier_reports_no_server_recovery_claim(self):
        from scripts.verify_delta_global_evidence import verify_reconnect_observation

        bundle = json.loads(
            (FIXTURES / "observed_global_btcusdt_client_reconnect_20260918.json")
            .read_text(encoding="utf-8")
        )
        verdict = verify_reconnect_observation(bundle)
        self.assertTrue(verdict.passed)
        self.assertTrue(any("not provider disconnects" in note
                            for note in verdict.limitations))


if __name__ == "__main__":
    unittest.main()
