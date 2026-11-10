"""Phase 207 durable restart-recovery tests for historical captures."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution.historical_capture_orchestrator import (
    CapturePersistenceError,
    CapturePlanError,
    HistoricalCaptureOrchestrator,
    HistoricalCapturePlan,
    _validate_page_provenance,
)


def _page_provenance(*, policy_enforced=True):
    return {
        "endpoint": "fills",
        "page_index": 0,
        "request_cursor": None,
        "response_cursor": None,
        "response_status": "SUCCESS",
        "record_count": 1,
        "request_started_at": "2026-10-01T00:00:00Z",
        "collected_at": "2026-10-01T00:00:00Z",
        "request_duration_ms": 1.0,
        "content_sha256": "a" * 64,
        "retry_count": 0,
        "http_status_code": 200,
        "request_policy_enforced": policy_enforced,
    }


def make_plan(**changes):
    values = dict(
        venue="delta",
        tenant_id="tenant-phase207",
        account_id="account-phase207",
        product_id=84,
        start="2026-10-01T00:00:00Z",
        end="2026-10-01T02:00:00Z",
        window_seconds=3600,
        overlap_seconds=0,
        repeat_count=1,
        endpoints=("fills",),
    )
    values.update(changes)
    return HistoricalCapturePlan(**values)


class SequenceAdapter:
    def __init__(self, statuses=("OK",), start_sequence=0):
        self.statuses = list(statuses)
        self.calls = []
        self.sequence = start_sequence

    def capture(self, **kwargs):
        self.calls.append(kwargs)
        status = self.statuses[min(self.sequence, len(self.statuses) - 1)]
        self.sequence += 1
        captured_at = f"2026-10-01T0{self.sequence}:00:00Z"
        return SimpleNamespace(
            captured_at=captured_at,
            fills=({"id": f"fill-{self.sequence}", "product_id": 84},),
            open_orders=(),
            order_history=(),
            positions=(),
            wallet_transactions=(),
            endpoint_status={"fills": status},
            page_provenance=(),
        )


class AuthenticatedSequenceAdapter(SequenceAdapter):
    def __init__(self, statuses=("OK",), start_sequence=0, *, policy_enforced=True,
                 include_page_provenance=True):
        super().__init__(statuses=statuses, start_sequence=start_sequence)
        self._rest = SimpleNamespace(
            authenticated=True,
            get_with_policy=lambda *args, **kwargs: None,
        )
        self.policy_enforced = policy_enforced
        self.include_page_provenance = include_page_provenance

    def capture(self, **kwargs):
        raw = super().capture(**kwargs)
        raw.page_provenance = (
            (_page_provenance(policy_enforced=self.policy_enforced),)
            if self.include_page_provenance else ()
        )
        return raw


class BudgetOverrunAdapter:
    def capture(self, **kwargs):
        page = _page_provenance(policy_enforced=False)
        page.update(
            response_status="RECORD_BUDGET_OVERRUN",
            record_count=3,
            records_not_persisted=1,
            record_budget_remaining=2,
        )
        return SimpleNamespace(
            captured_at="2026-10-01T00:30:00Z",
            fills=(
                {"id": "fill-1", "product_id": 84},
                {"id": "fill-2", "product_id": 84},
            ),
            open_orders=(), order_history=(), positions=(), wallet_transactions=(),
            endpoint_status={"fills": "RECORD_BUDGET_OVERRUN"},
            page_provenance=(page,),
        )


def test_restart_skips_verified_complete_endpoint_window_slots(tmp_path):
    plan = make_plan()
    first_adapter = SequenceAdapter()
    first = HistoricalCaptureOrchestrator(first_adapter, tmp_path).run(plan)

    assert first.status == "COMPLETE"
    assert first.completed_windows == 2
    assert len(first_adapter.calls) == 2

    restarted_adapter = SequenceAdapter()
    resumed = HistoricalCaptureOrchestrator(restarted_adapter, tmp_path).run(plan)

    assert resumed.status == "COMPLETE"
    assert resumed.completed_windows == 2
    assert resumed.snapshots == first.snapshots
    assert resumed.total_records == first.total_records
    assert restarted_adapter.calls == []


def test_restart_retries_partial_slot_without_overwriting_prior_evidence(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    first_adapter = SequenceAdapter(statuses=("TEMPORARY_FAILURE",))
    first = HistoricalCaptureOrchestrator(first_adapter, tmp_path).run(plan)

    assert first.status == "PARTIAL"
    assert len(first.snapshots) == 1
    assert first.snapshots[0].complete is False

    artifacts_before = sorted(path.read_bytes() for path in Path(tmp_path).rglob("*.json"))
    retry_adapter = SequenceAdapter(statuses=("OK",), start_sequence=1)
    resumed = HistoricalCaptureOrchestrator(retry_adapter, tmp_path).run(plan)

    assert resumed.status == "COMPLETE"
    assert resumed.completed_windows == 1
    assert len(retry_adapter.calls) == 1
    assert retry_adapter.calls[0]["endpoints"] == ("fills",)
    artifacts_after = sorted(path.read_bytes() for path in Path(tmp_path).rglob("*.json"))
    assert len(artifacts_after) == 2
    assert artifacts_before[0] in artifacts_after
    assert sum(not snap.complete for snap in resumed.snapshots) == 1
    assert sum(snap.complete for snap in resumed.snapshots) == 1


def test_resume_fails_closed_when_persisted_capture_is_corrupt(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"]["records"][0]["tampered"] = True
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="could not be verified"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_capture_identity_not_derived_from_its_slot(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"]["captured_at"] = "2026-10-01T09:00:00Z"
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="identity does not match its slot"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_malformed_or_out_of_scope_page_provenance(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["page_provenance"] = [{"endpoint": "unknown", "page_index": 0}]
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="page provenance endpoint is unsupported"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_page_provenance_over_total_page_budget(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", max_total_pages=1)
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["page_provenance"] = [{}, {}]
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="exceeds the total page budget"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_can_be_disabled_explicitly(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    first = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert first.status == "COMPLETE"

    adapter = SequenceAdapter(start_sequence=5)
    rerun = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan, resume=False)
    assert rerun.status == "COMPLETE"
    assert len(adapter.calls) == 1


def test_resume_rejects_unknown_artifact_schema_instead_of_silently_skipping(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["schema"] = "quantengine.unknown.capture.v99"
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="schema is unsupported"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


@pytest.mark.parametrize("unsafe_plan_id", ("../escape", "nested/escape", r"nested\\escape", ".."))
def test_plan_id_cannot_escape_capture_storage_root(tmp_path, unsafe_plan_id):
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id=unsafe_plan_id)
    with pytest.raises(CapturePlanError, match="safe single path component"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_adjacent_windows_are_reconciled_without_treating_absence_as_deletion(tmp_path):
    plan = make_plan()
    class RepeatedIdentityAdapter:
        def __init__(self):
            self.calls = 0

        def capture(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                captured_at=f"2026-10-01T0{self.calls}:00:00Z",
                fills=({"id": "fill-shared", "product_id": 84, "price": "100"},),
                open_orders=(),
                order_history=(),
                positions=(),
                wallet_transactions=(),
                endpoint_status={"fills": "OK"},
                page_provenance=(),
            )

    result = HistoricalCaptureOrchestrator(RepeatedIdentityAdapter(), tmp_path).run(plan)

    assert result.status == "COMPLETE"
    assert len(result.cross_window_reconciliation_reports) == 1
    cross_window = result.cross_window_reconciliation_reports[0]
    assert cross_window["earlier_window_index"] == 0
    assert cross_window["later_window_index"] == 1
    assert cross_window["endpoint"] == "fills"
    assert cross_window["status"] == "RECONCILED"
    assert cross_window["result"]["record_counts"]["unchanged"] == 1
    assert cross_window["result"]["not_observed"] == []


def test_resume_reconstructs_same_window_repeat_reconciliation_reports(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", repeat_count=2)
    first = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert first.status == "COMPLETE"
    assert first.requested_windows == 2
    assert first.completed_windows == 2
    assert len(first.reconciliation_reports) == 1

    restarted = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert restarted.status == "COMPLETE"
    assert len(restarted.reconciliation_reports) == 1
    assert restarted.reconciliation_reports[0]["result"]["record_counts"]["unchanged"] == 0
    assert restarted.reconciliation_reports[0]["status"] == "RECONCILED_WITH_DIFFERENCES"


def test_completed_recovered_slots_do_not_consume_capture_run_budget(tmp_path):
    plan = make_plan(max_capture_runs=1)
    # First pass can only capture the first of two planned windows.
    first = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert first.status == "PARTIAL"
    assert len(first.snapshots) == 1

    # The one remaining read is allowed after recovery; the completed slot
    # does not consume the new process's capture-run budget.
    adapter = SequenceAdapter(start_sequence=5)
    resumed = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan)
    assert resumed.status == "COMPLETE"
    assert len(adapter.calls) == 1
    assert resumed.completed_windows == 2


def test_resume_rejects_missing_capture_content_checksum(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"].pop("raw_source_checksum")
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="content checksum is missing"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_inconsistent_capture_record_count(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"]["record_count"] += 1
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="record count is missing or inconsistent"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)



@pytest.mark.parametrize("captured_at", (None, "not-a-timestamp"))
def test_resume_rejects_invalid_capture_timestamp(tmp_path, captured_at):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    if captured_at is None:
        payload["capture"].pop("captured_at")
    else:
        payload["capture"]["captured_at"] = captured_at
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="timestamp is invalid"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_endpoint_status_that_contradicts_completeness(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"]["endpoint_status"]["fills"] = "TEMPORARY_FAILURE"
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="contradicts completeness flags"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_rejects_non_boolean_completeness_flags(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["capture"]["complete"] = "false"
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="completeness flags must be booleans"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)



def test_resume_rejects_changed_plan_under_same_explicit_plan_id(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id="phase207-plan-fingerprint")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)

    changed_plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-plan-fingerprint",
        retry_budget=plan.retry_budget + 1,
    )
    with pytest.raises(CapturePersistenceError, match="plan fingerprint"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(changed_plan)


def test_authenticated_capture_rejects_unenforced_request_policy_before_persisting(tmp_path):
    plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-auth-policy-new",
        mode="authenticated",
    )
    adapter = AuthenticatedSequenceAdapter(policy_enforced=False)
    result = HistoricalCaptureOrchestrator(
        adapter, tmp_path, owner_authorizer=lambda _: True
    ).run(plan)

    assert result.status == "PARTIAL"
    assert result.snapshots == []
    assert result.errors and "CapturePersistenceError" in result.errors[0]
    assert list(Path(tmp_path).rglob("*.json")) == []


def test_authenticated_resume_rejects_unenforced_request_policy(tmp_path):
    plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-auth-policy-resume",
        mode="authenticated",
    )
    first = HistoricalCaptureOrchestrator(
        AuthenticatedSequenceAdapter(policy_enforced=True),
        tmp_path,
        owner_authorizer=lambda _: True,
    ).run(plan)
    assert first.status == "COMPLETE"

    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["page_provenance"][0]["request_policy_enforced"] = False
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="bounded request policy"):
        HistoricalCaptureOrchestrator(
            AuthenticatedSequenceAdapter(policy_enforced=True),
            tmp_path,
            owner_authorizer=lambda _: True,
        ).run(plan)



def test_resume_rejects_fixture_artifact_reused_as_authenticated_plan(tmp_path):
    fixture_plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-mode-fingerprint",
        mode="fixture",
    )
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(fixture_plan)

    authenticated_plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-mode-fingerprint",
        mode="authenticated",
    )
    adapter = AuthenticatedSequenceAdapter()
    with pytest.raises(CapturePersistenceError, match="plan fingerprint"):
        HistoricalCaptureOrchestrator(
            adapter, tmp_path, owner_authorizer=lambda _: True
        ).run(authenticated_plan)
    assert adapter.calls == []


def test_resume_rejects_legacy_phase207_artifact_with_explicit_plan_id(tmp_path):
    plan = make_plan(
        end="2026-10-01T01:00:00Z",
        plan_id="phase207-legacy-explicit-id",
    )
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["schema"] = "quantengine.phase207.capture.v1"
    payload.pop("plan_fingerprint")
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="explicit plan_id"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_accepts_legacy_phase207_artifact_with_derived_plan_id(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["schema"] = "quantengine.phase207.capture.v1"
    payload.pop("plan_fingerprint")
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    resumed = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert resumed.status == "COMPLETE"
    assert resumed.snapshots


def test_resume_persists_page_budget_overrun_with_raw_count_above_snapshot_limit(tmp_path):
    plan = make_plan(
        end="2026-10-01T01:00:00Z",
        max_records_per_snapshot=2,
        max_total_records=10,
    )
    result = HistoricalCaptureOrchestrator(BudgetOverrunAdapter(), tmp_path).run(plan)

    assert result.status == "PARTIAL"
    assert len(result.snapshots) == 1
    assert len(result.snapshots[0].records) == 2
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    page = payload["page_provenance"][0]
    assert page["response_status"] == "RECORD_BUDGET_OVERRUN"
    assert page["record_count"] == 3
    assert page["records_not_persisted"] == 1


def test_page_provenance_accepts_only_known_delta_routes_for_selected_endpoints():
    plan = make_plan(endpoints=("open_orders",))
    page = _page_provenance()
    page["endpoint"] = "/v2/orders"
    _validate_page_provenance([page], plan)

    page["endpoint"] = "/v2/unknown"
    with pytest.raises(CapturePersistenceError, match="endpoint is unsupported"):
        _validate_page_provenance([page], plan)
