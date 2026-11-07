"""Phase 207 durable restart-recovery tests for historical captures."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution.historical_capture_orchestrator import (
    CapturePersistenceError,
    HistoricalCaptureOrchestrator,
    HistoricalCapturePlan,
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
    artifact.write_text('{"schema":"quantengine.phase207.capture.v1","capture":{}}', encoding="utf-8")

    with pytest.raises(CapturePersistenceError, match="could not be verified"):
        HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)


def test_resume_can_be_disabled_explicitly(tmp_path):
    plan = make_plan(end="2026-10-01T01:00:00Z")
    first = HistoricalCaptureOrchestrator(SequenceAdapter(), tmp_path).run(plan)
    assert first.status == "COMPLETE"

    adapter = SequenceAdapter(start_sequence=5)
    rerun = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan, resume=False)
    assert rerun.status == "COMPLETE"
    assert len(adapter.calls) == 1
