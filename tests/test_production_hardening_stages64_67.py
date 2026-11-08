from dataclasses import replace

from core.governance.production_hardening_stages64_67 import (
    AuditCoverage, CredentialExposureClosure, RepositorySnapshotIntegrity,
    StrategyRecertification, evaluate_audit_coverage, evaluate_credential_exposure,
    evaluate_repository_snapshot, evaluate_strategy_recertification,
)

COMMIT = "a" * 40
DIGEST = "b" * 64


def credential():
    return CredentialExposureClosure(COMMIT, "exposure.csv", "provider-revocation.pdf",
        "history-remediation.md", "independent-review.md", "2026-11-08T12:00:00Z",
        2, 0, True, True, True)


def repository():
    return RepositorySnapshotIntegrity(COMMIT, DIGEST, "git-status.txt", "lock-disposition.md",
        "clean-checkout.json", "independent-review.md", "2026-11-08T12:00:00Z",
        0, 0, True, True)


def strategy():
    return StrategyRecertification(COMMIT, DIGEST, "c" * 64, "canonicalization.md",
        "independent-reproduction.json", "preregistration.json", DIGEST, "oos-report.pdf",
        "independent-review.md", "2026-11-08T12:00:00Z", 1000, 0, True, True, True, True)


def audit():
    return AuditCoverage(COMMIT, "scope.csv", "findings.csv", "evidence.csv",
        "independent-review.md", "2026-11-08T12:00:00Z", 107, 107, 0, 0, 0, True)


def test_all_four_stages_are_unverified_not_authorized():
    results = (evaluate_credential_exposure(credential()),
               evaluate_repository_snapshot(repository()),
               evaluate_strategy_recertification(strategy()),
               evaluate_audit_coverage(audit()))
    assert [x.stage for x in results] == [64, 65, 66, 67]
    assert all(x.status.endswith("UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)


def test_credential_exposure_requires_provider_and_history_closure():
    result = evaluate_credential_exposure(replace(credential(),
        provider_revocation_confirmed=False, unresolved_exposures=1))
    assert result.status == "CREDENTIAL_EXPOSURE_HOLD"
    assert any("provider_revocation_confirmed" in x for x in result.reasons)
    assert any("unresolved_exposures" in x for x in result.reasons)


def test_repository_snapshot_rejects_dirty_tree_and_stale_lock():
    result = evaluate_repository_snapshot(replace(repository(),
        uncommitted_paths=1313, unresolved_index_locks=1))
    assert result.status == "REPOSITORY_SNAPSHOT_HOLD"
    assert len(result.reasons) >= 2


def test_strategy_recertification_requires_reproducible_oos_chain():
    result = evaluate_strategy_recertification(replace(strategy(),
        hash_reproduced=False, oos_observations=0, leakage_findings=1))
    assert result.status == "STRATEGY_RECERTIFICATION_HOLD"
    assert len(result.reasons) >= 3


def test_audit_coverage_rejects_unknown_controls_and_open_p0():
    result = evaluate_audit_coverage(replace(audit(),
        controls_audited=12, unknown_controls=95, unresolved_p0_findings=1))
    assert result.status == "AUDIT_COVERAGE_HOLD"
    assert len(result.reasons) >= 3
