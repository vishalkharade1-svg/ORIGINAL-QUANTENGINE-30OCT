from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution.historical_capture_orchestrator import (
    CaptureAuthorizationError, CapturePlanError, HistoricalCapturePlan,
    HistoricalCaptureOrchestrator, generate_windows, observation_stability,
)


def plan(**changes):
    values = dict(venue="delta", tenant_id="tenant-a", account_id="account-a",
                  product_id=84, start="2026-10-01T00:00:00Z",
                  end="2026-10-01T03:00:00Z", window_seconds=3600,
                  overlap_seconds=300, mode="fixture")
    values.update(changes)
    return HistoricalCapturePlan(**values)


def test_window_generation_is_deterministic_and_overlapping():
    windows = generate_windows(plan())
    assert windows == generate_windows(plan())
    assert len(windows) == 4
    assert windows[0].end - windows[1].start == __import__("datetime").timedelta(seconds=300)
    assert windows[-1].end.isoformat() == "2026-10-01T03:00:00+00:00"


def test_timezone_normalized_to_utc():
    windows = generate_windows(plan(start="2026-10-01T05:30:00+05:30",
                                    end="2026-10-01T08:30:00+05:30"))
    assert windows[0].start.tzinfo == timezone.utc


@pytest.mark.parametrize("changes", [
    {"start": "2026-10-02T00:00:00Z"},
    {"end": "2026-10-20T00:00:00Z"},
    {"window_seconds": 0},
    {"repeat_count": 11},
    {"max_windows": 0},
    {"max_total_records": 0},
    {"mode": "unknown"},
    {"tenant_id": ""},
])
def test_invalid_or_unbounded_plan_rejected(changes):
    with pytest.raises(CapturePlanError):
        generate_windows(plan(**changes))


def test_window_budget_enforced():
    with pytest.raises(CapturePlanError, match="maximum window"):
        generate_windows(plan(max_windows=1))


def test_authenticated_requires_trusted_authorization(tmp_path):
    authenticated_plan = plan(mode="authenticated", owner_authorized=True)
    with pytest.raises(CaptureAuthorizationError):
        HistoricalCaptureOrchestrator(FakeAdapter(), tmp_path).run(authenticated_plan)


class FakeAdapter:
    def __init__(self, rows=None, complete=True):
        self._rest = SimpleNamespace(authenticated=False)
        self.rows = rows or [{"id": "o-1", "product_id": 84, "size": "1"}]
        self.complete = complete
        self.calls = []

    def capture(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            captured_at="2026-10-01T04:00:00Z", product_id=84,
            open_orders=tuple(self.rows), order_history=(), fills=(),
            positions=(), wallet_transactions=(), complete=self.complete,
            endpoint_status={"open_orders": "OK" if self.complete else "INCOMPLETE_PAGINATION"},
        )


def test_orchestrator_persists_capture_and_preserves_scope(tmp_path):
    adapter = FakeAdapter()
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan())
    assert result.status == "COMPLETE"
    assert result.completed_windows == 4
    files = list(Path(tmp_path).rglob("*.json"))
    assert len(files) == 4
    assert all('"tenant_id":"tenant-a"' in f.read_text() for f in files)


def test_incomplete_capture_is_partial(tmp_path):
    result = HistoricalCaptureOrchestrator(FakeAdapter(complete=False), tmp_path).run(plan())
    assert result.status == "PARTIAL"
    assert all(not snap.complete for snap in result.snapshots)


def test_record_budget_stops_capture(tmp_path):
    adapter = FakeAdapter(rows=[{"id": str(i)} for i in range(3)])
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan(max_records_per_snapshot=2))
    assert result.status == "PARTIAL"
    assert result.snapshots == []


def test_stability_does_not_infer_deletion():
    from core.execution.cross_capture_reconciliation import CaptureSnapshot
    first = CaptureSnapshot("a", "delta", "orders", ({"id": "1"},),
                            "2026-10-01T00:00:00Z", account_id="a",
                            complete=True, pagination_complete=True)
    second = CaptureSnapshot("b", "delta", "orders", (),
                             "2026-10-01T00:01:00Z", account_id="a",
                             complete=True, pagination_complete=True)
    report = observation_stability([first, second])
    assert report["records"][0]["status"] == "NOT_OBSERVED_IN_SOME_CAPTURES"
    assert "deleted" in report["disclaimer"]
