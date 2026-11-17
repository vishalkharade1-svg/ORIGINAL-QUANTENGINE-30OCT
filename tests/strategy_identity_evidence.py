"""Assertions for an observed but unregistered strategy identity snapshot.

This helper deliberately does not bless the current hashes as a new strategy
registration. It verifies that the current source matches the explicit
PHASE206 forensic observation and that the release gate remains blocked.
"""
from __future__ import annotations

import json
from pathlib import Path


def assert_unregistered_identity(case, identities: dict, root: Path) -> None:
    root = Path(root)
    report = json.loads(
        (root / "reports" / "PHASE206_RELEASE_GATES.json").read_text(
            encoding="utf-8"
        )
    )
    observation = report["strategy_identity_observation"]
    baseline = observation["phase22_registered_baseline"]
    observed = observation["observed_current_unregistered"]

    case.assertEqual(report["gates"]["strategy_identity"],
                     "BLOCKED_UNREGISTERED_CURRENT_IDENTITY_DRIFT")
    case.assertEqual(observation["status"], "OBSERVED_UNREGISTERED")
    case.assertIs(observation["approved_for_research"], False)
    case.assertEqual(
        identities["historical_phase14_pinned_hash"],
        observation["historical_phase14_pin"],
    )
    case.assertEqual(identities["strategy_core"]["sha256"],
                     observed["strategy_core"])
    case.assertEqual(identities["runtime_infrastructure"]["sha256"],
                     observed["runtime_infrastructure"])
    case.assertEqual(
        identities["composite_legacy_9_files"]["canonical_lf_sha256"],
        observed["composite_legacy_9_files"],
    )
    case.assertNotEqual(identities["strategy_core"]["sha256"],
                        baseline["strategy_core"])
    case.assertNotEqual(identities["runtime_infrastructure"]["sha256"],
                        baseline["runtime_infrastructure"])
    case.assertNotEqual(
        identities["composite_legacy_9_files"]["canonical_lf_sha256"],
        baseline["composite_legacy_9_files"],
    )
