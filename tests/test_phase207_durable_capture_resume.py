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




def test_resume_rejects_changed_collection_policy_under_same_explicit_plan_id(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id="stable-plan")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)

    changed = make_plan(
        end="2026-10-01T01:00:00Z", plan_id="stable-plan", retry_budget=3
    )
    with pytest.raises(CapturePersistenceError, match="plan/policy fingerprint"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(changed)


def test_resume_rejects_changed_adapter_source_identity_under_same_plan_id(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id="stable-plan")
    first_adapter = SequenceAdapter()
    first_adapter.provenance_identity = {"source": "delta-fixture-a", "api_version": "v1"}
    HistoricalCaptureOrchestrator(first_adapter, tmp_path).run(plan)

    changed_adapter = SequenceAdapter()
    changed_adapter.provenance_identity = {"source": "delta-fixture-b", "api_version": "v1"}
    with pytest.raises(CapturePersistenceError, match="adapter/source identity"):
        HistoricalCaptureOrchestrator(changed_adapter, tmp_path).run(plan)


def test_resume_rejects_fixture_artifacts_for_authenticated_mode(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id="stable-plan")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)

    authenticated_adapter = SequenceAdapter()
    authenticated_adapter._rest = SimpleNamespace(
        authenticated=True,
        provenance_identity={"origin": "https://testnet.delta.example", "api_version": "v1"},
        get_with_policy=lambda *args, **kwargs: None,
    )
    authenticated_adapter.provenance_identity = {
        "source": "delta-production", "api_version": "v1"
    }
    authenticated_plan = make_plan(
        end="2026-10-01T01:00:00Z", plan_id="stable-plan", mode="authenticated"
    )
    orchestrator = HistoricalCaptureOrchestrator(
        authenticated_adapter, tmp_path, owner_authorizer=lambda _: True
    )
    with pytest.raises(CapturePersistenceError, match="plan/policy fingerprint"):
        orchestrator.run(authenticated_plan)
    assert authenticated_adapter.calls == []


def test_resume_rejects_malformed_page_provenance(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    artifact = next(Path(tmp_path).rglob("*.json"))
    payload = __import__("json").loads(artifact.read_text(encoding="utf-8"))
    payload["page_provenance"] = {"not": "a-list"}
    artifact.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="page provenance"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_invalid_new_page_provenance_stops_capture_without_becoming_partial(tmp_path):
    plan = make_plan()
    class InvalidProvenanceAdapter(SequenceAdapter):
        def capture(self, **kwargs):
            result = super().capture(**kwargs)
            result.page_provenance = [{}]
            return result

    adapter = InvalidProvenanceAdapter()
    with pytest.raises(CapturePersistenceError, match="page provenance"):
        HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan)
    assert len(adapter.calls) == 1
    assert list(Path(tmp_path).rglob("*.json")) == []



def test_authenticated_capture_requires_explicit_non_secret_source_identity(tmp_path):
    adapter = SequenceAdapter()
    adapter._rest = SimpleNamespace(
        authenticated=True, get_with_policy=lambda *args, **kwargs: None
    )
    plan = make_plan(
        end="2026-10-01T01:00:00Z", mode="authenticated", plan_id="authenticated-plan"
    )
    orchestrator = HistoricalCaptureOrchestrator(
        adapter, tmp_path, owner_authorizer=lambda _: True
    )
    with pytest.raises(CapturePlanError, match="stable non-secret provenance_identity"):
        orchestrator.run(plan)
    assert adapter.calls == []



def test_adapter_source_identity_change_during_capture_fails_closed(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    class ChangingSourceAdapter(SequenceAdapter):
        def __init__(self):
            super().__init__()
            self.provenance_identity = {"source": "delta-fixture-a", "api_version": "v1"}

        def capture(self, **kwargs):
            result = super().capture(**kwargs)
            self.provenance_identity = {"source": "delta-fixture-b", "api_version": "v1"}
            return result

    adapter = ChangingSourceAdapter()
    with pytest.raises(CapturePersistenceError, match="changed during capture"):
        HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan)
    assert len(adapter.calls) == 1
    assert list(Path(tmp_path).rglob("*.json")) == []



def test_artifact_records_non_secret_adapter_identity_for_audit(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    adapter = SequenceAdapter()
    adapter.provenance_identity = {"source": "delta-fixture", "api_version": "v1"}
    HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan)

    payload = __import__("json").loads(
        next(Path(tmp_path).rglob("*.json")).read_text(encoding="utf-8")
    )
    assert payload["schema"] == "quantengine.phase208.capture.v1"
    assert payload["adapter_identity"]["adapter_class"].endswith("SequenceAdapter")
    assert payload["adapter_identity"]["adapter_source"] == {
        "source": "delta-fixture", "api_version": "v1"
    }
    assert len(payload["adapter_fingerprint"]) == 64


def test_adapter_identity_rejects_credential_like_metadata_fields(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    adapter = SequenceAdapter()
    adapter.provenance_identity = {"source": "delta-fixture", "api_key": "must-not-persist"}

    with pytest.raises(CapturePlanError, match="credential-like"):
        HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan)
    assert adapter.calls == []



def test_resume_rejects_plan_directory_symlink_escape(tmp_path):
    storage_root = tmp_path / "storage"
    outside = tmp_path / "outside"
    storage_root.mkdir()
    outside.mkdir()
    (storage_root / "symlink-plan").symlink_to(outside, target_is_directory=True)
    adapter = SequenceAdapter()
    plan = make_plan(end="2026-10-01T01:00:00Z", plan_id="symlink-plan")

    with pytest.raises(CapturePersistenceError, match="plan directory"):
        HistoricalCaptureOrchestrator(adapter, storage_root).run(plan)
    assert adapter.calls == []


def test_resume_rejects_symlinked_artifact_file(tmp_path):
    storage_root = tmp_path / "storage"
    plan_dir = storage_root / "symlink-artifact-plan"
    plan_dir.mkdir(parents=True)
    outside_file = tmp_path / "outside.json"
    outside_file.write_text('{"schema":"quantengine.phase208.capture.v1"}', encoding="utf-8")
    (plan_dir / "linked.json").symlink_to(outside_file)
    adapter = SequenceAdapter()
    plan = make_plan(
        end="2026-10-01T01:00:00Z", plan_id="symlink-artifact-plan"
    )

    with pytest.raises(CapturePersistenceError, match="opened safely"):
        HistoricalCaptureOrchestrator(adapter, storage_root).run(plan)
    assert adapter.calls == []



def _authenticated_page_provenance(**overrides):
    page = {
        "endpoint": "fills",
        "page_index": 0,
        "request_cursor": None,
        "response_cursor": None,
        "response_status": "SUCCESS",
        "record_count": 0,
        "content_sha256": "a" * 64,
        "request_started_at": "2026-10-01T00:00:00Z",
        "collected_at": "2026-10-01T00:00:01Z",
        "request_duration_ms": 1000.0,
        "retry_count": 0,
        "http_status_code": 200,
        "request_policy_enforced": True,
    }
    page.update(overrides)
    return page


def test_authenticated_capture_requires_per_page_policy_evidence():
    plan = make_plan(mode="authenticated")
    with pytest.raises(CapturePersistenceError, match="missing per-page request-policy provenance"):
        _validate_page_provenance([], plan, require_enforced_policy=True)


def test_authenticated_capture_rejects_pages_without_bounded_policy():
    plan = make_plan(mode="authenticated")
    with pytest.raises(CapturePersistenceError, match="did not enforce bounded request policy"):
        _validate_page_provenance(
            [_authenticated_page_provenance(request_policy_enforced=False)],
            plan,
            require_enforced_policy=True,
        )


def test_authenticated_success_page_requires_bounded_retry_and_http_evidence():
    plan = make_plan(mode="authenticated")
    with pytest.raises(CapturePersistenceError, match="lacks bounded retry/HTTP evidence"):
        _validate_page_provenance(
            [_authenticated_page_provenance(retry_count=None)],
            plan,
            require_enforced_policy=True,
        )



@pytest.mark.parametrize(
    "overrides",
    [
        {"endpoint": []},
        {"response_status": []},
    ],
)
def test_authenticated_page_provenance_rejects_unhashable_fields(overrides):
    plan = make_plan(mode="authenticated")
    with pytest.raises(CapturePersistenceError, match="endpoint is unsupported|response status is unsupported"):
        _validate_page_provenance(
            [_authenticated_page_provenance(**overrides)],
            plan,
            require_enforced_policy=True,
        )



def test_authenticated_capture_requires_rest_origin_identity_not_only_adapter_label(tmp_path):
    adapter = SequenceAdapter()
    adapter._rest = SimpleNamespace(
        authenticated=True, get_with_policy=lambda *args, **kwargs: None
    )
    adapter.provenance_identity = {"adapter": "delta-read-adapter"}
    plan = make_plan(
        end="2026-10-01T01:00:00Z", mode="authenticated", plan_id="authenticated-plan"
    )
    orchestrator = HistoricalCaptureOrchestrator(
        adapter, tmp_path, owner_authorizer=lambda _: True
    )
    with pytest.raises(CapturePlanError, match="REST client must expose a stable non-secret provenance_identity"):
        orchestrator.run(plan)
    assert adapter.calls == []

def test_authenticated_resume_validates_page_provenance_per_endpoint_slot(tmp_path):
    plan = make_plan(
        end="2026-10-01T01:00:00Z",
        endpoints=("fills", "positions"),
        mode="authenticated",
    )

    class PartialAuthenticatedAdapter:
        def __init__(self):
            self.calls = []
            self.sequence = 0
            self.provenance_identity = {"adapter": "phase207-resume-fixture"}
            self._rest = SimpleNamespace(
                authenticated=True,
                provenance_identity={
                    "venue": "delta",
                    "origin": "https://testnet.delta.example",
                    "api_version": "v2",
                },
                get_with_policy=lambda *args, **kwargs: None,
            )

        def capture(self, **kwargs):
            self.calls.append(kwargs)
            self.sequence += 1
            endpoints = kwargs["endpoints"]
            failed_positions = self.sequence == 1
            statuses = {
                endpoint: (
                    "REQUEST_FAILED"
                    if endpoint == "positions" and failed_positions
                    else "OK"
                )
                for endpoint in endpoints
            }
            pages = []
            for endpoint in endpoints:
                failed = endpoint == "positions" and failed_positions
                pages.append({
                    "endpoint": endpoint,
                    "page_index": 0,
                    "request_cursor": None,
                    "response_cursor": None,
                    "response_status": "REQUEST_FAILED" if failed else "SUCCESS",
                    "record_count": 0,
                    "content_sha256": None if failed else "a" * 64,
                    "request_started_at": "2026-10-01T00:00:00Z",
                    "collected_at": "2026-10-01T00:00:01Z",
                    "request_duration_ms": 1.0,
                    "retry_count": 0,
                    "http_status_code": 503 if failed else 200,
                    "request_policy_enforced": True,
                })
            return SimpleNamespace(
                captured_at=f"2026-10-01T0{self.sequence}:00:00Z",
                fills=(),
                positions=(),
                open_orders=(),
                order_history=(),
                wallet_transactions=(),
                endpoint_status=statuses,
                page_provenance=tuple(pages),
            )

    first_adapter = PartialAuthenticatedAdapter()
    first = HistoricalCaptureOrchestrator(
        first_adapter, tmp_path, owner_authorizer=lambda _: True
    ).run(plan)
    assert first.status == "PARTIAL"
    assert len(first_adapter.calls) == 1
    assert first_adapter.calls[0]["endpoints"] == ("fills", "positions")

    resumed_adapter = PartialAuthenticatedAdapter()
    resumed_adapter.sequence = 1
    resumed = HistoricalCaptureOrchestrator(
        resumed_adapter, tmp_path, owner_authorizer=lambda _: True
    ).run(plan)
    assert resumed.status == "COMPLETE"
    assert len(resumed_adapter.calls) == 1
    assert resumed_adapter.calls[0]["endpoints"] == ("positions",)
    assert resumed.completed_windows == 1

