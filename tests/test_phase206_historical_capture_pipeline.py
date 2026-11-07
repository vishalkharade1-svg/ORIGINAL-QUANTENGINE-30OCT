from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution.historical_capture_orchestrator import (
    CaptureAuthorizationError, CapturePersistenceError, CapturePlanError, HistoricalCapturePlan,
    HistoricalCaptureOrchestrator, _safe_json_write, generate_windows, observation_stability,
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
    {"endpoints": ()},
    {"endpoints": ("fills", "fills")},
    {"endpoints": ("unsupported",)},
    {"endpoints": ([],)},
])
def test_invalid_or_unbounded_plan_rejected(changes):
    with pytest.raises(CapturePlanError):
        generate_windows(plan(**changes))


def test_window_budget_enforced():
    with pytest.raises(CapturePlanError, match="maximum window"):
        generate_windows(plan(max_windows=1))


def test_authenticated_requires_trusted_authorization_callback(tmp_path):
    authenticated_plan = plan(mode="authenticated")
    with pytest.raises(CaptureAuthorizationError, match="trusted owner authorization"):
        HistoricalCaptureOrchestrator(FakeAdapter(), tmp_path).run(authenticated_plan)


def test_plan_boolean_cannot_grant_authenticated_access(tmp_path):
    authenticated_plan = plan(mode="authenticated")
    adapter = FakeAdapter()
    adapter._rest.authenticated = True
    orchestrator = HistoricalCaptureOrchestrator(
        adapter, tmp_path, owner_authorizer=lambda _: False
    )
    with pytest.raises(CaptureAuthorizationError, match="denied"):
        orchestrator.run(authenticated_plan)


def test_trusted_callback_and_authenticated_fake_adapter_allow_fixture_exercise(tmp_path):
    authenticated_plan = plan(mode="authenticated")
    adapter = FakeAdapter()
    adapter._rest.authenticated = True
    result = HistoricalCaptureOrchestrator(
        adapter, tmp_path, owner_authorizer=lambda _: True
    ).run(authenticated_plan)
    assert result.status == "COMPLETE"


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
            endpoint_status={
                "open_orders": "OK" if self.complete else "INCOMPLETE_PAGINATION",
                "order_history": "OK", "fills": "OK", "positions": "OK",
                "wallet_transactions": "OK",
            },
        )


def test_orchestrator_persists_capture_and_preserves_scope(tmp_path):
    adapter = FakeAdapter()
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan())
    assert result.status == "COMPLETE"
    assert result.completed_windows == 4
    files = list(Path(tmp_path).rglob("*.json"))
    assert len(files) == 20
    assert all('"tenant_id":"tenant-a"' in f.read_text() for f in files)


def test_incomplete_capture_is_partial(tmp_path):
    result = HistoricalCaptureOrchestrator(FakeAdapter(complete=False), tmp_path).run(plan())
    assert result.status == "PARTIAL"
    assert len(result.snapshots) == 20
    open_orders = [snap for snap in result.snapshots if snap.record_category == "open_orders"]
    assert len(open_orders) == 4
    assert all(not snap.complete for snap in open_orders)
    assert all(snap.complete for snap in result.snapshots if snap.record_category != "open_orders")


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



def test_total_record_budget_stops_further_adapter_reads(tmp_path):
    adapter = FakeAdapter()
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(
        plan(max_total_records=1)
    )
    assert result.status == "PARTIAL"
    assert result.total_records == 1
    assert len(adapter.calls) == 2
    assert result.errors[-1].endswith("MAX_TOTAL_RECORDS_REACHED")


def test_repeated_captures_reconcile_against_prior_observation(tmp_path):
    adapter = FakeAdapter()
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(
        plan(repeat_count=2)
    )
    assert result.status == "COMPLETE"
    assert result.completed_windows == 8
    assert len(result.reconciliation_reports) == 20
    assert all(report["status"] == "RECONCILED"
               for report in result.reconciliation_reports)


def test_orchestrator_uses_only_adapter_capture_method(tmp_path):
    class ReadOnlyAdapter:
        def __init__(self):
            self.calls = 0

        def capture(self, **kwargs):
            self.calls += 1
            return FakeAdapter().capture(**kwargs)

    adapter = ReadOnlyAdapter()
    result = HistoricalCaptureOrchestrator(adapter, tmp_path).run(plan())
    assert result.status == "COMPLETE"
    assert adapter.calls == result.completed_windows



def test_atomic_persistence_is_immutable_and_idempotent(tmp_path):
    target = tmp_path / "capture" / "snapshot"
    first = _safe_json_write(target, {"records": [{"id": "a"}]})
    second = _safe_json_write(target, {"records": [{"id": "a"}]})
    assert first == second
    artifact = target.with_suffix(".json")
    assert artifact.exists()
    assert not list(artifact.parent.glob("*.tmp"))
    with pytest.raises(CapturePersistenceError, match="different content"):
        _safe_json_write(target, {"records": [{"id": "b"}]})
    assert artifact.read_text() == '{"records":[{"id":"a"}]}'


def test_endpoint_snapshots_are_isolated_and_wallet_is_not_product_scoped(tmp_path):
    class MultiEndpointAdapter:
        def capture(self, **kwargs):
            return SimpleNamespace(
                captured_at="2026-10-01T04:00:00Z",
                open_orders=({"id": "same-id", "status": "open"},),
                order_history=({"id": "same-id", "status": "closed"},),
                fills=({"id": "same-id", "order_id": "same-id"},),
                positions=({"id": "same-id", "size": "1", "query_product_id": 84},),
                wallet_transactions=({"id": "same-id", "amount": "1"},),
                complete=True,
                endpoint_status={
                    "open_orders": "OK", "order_history": "OK", "fills": "OK",
                    "positions": "OK", "wallet_transactions": "OK",
                },
            )

    result = HistoricalCaptureOrchestrator(MultiEndpointAdapter(), tmp_path).run(plan())
    assert result.status == "COMPLETE"
    assert {snap.record_category for snap in result.snapshots} == {
        "open_orders", "order_history", "fills", "positions", "wallet_transactions"
    }
    assert len({snap.record_category for snap in result.snapshots}) == 5
    wallet = next(snap for snap in result.snapshots if snap.record_category == "wallet_transactions")
    assert wallet.product_id is None
    assert wallet.records[0]["id"] == "same-id"


def test_capture_plan_can_limit_endpoint_scope(tmp_path):
    result = HistoricalCaptureOrchestrator(FakeAdapter(), tmp_path).run(
        plan(endpoints=("fills",))
    )
    assert result.status == "COMPLETE"
    assert len(result.snapshots) == 4
    assert all(snap.record_category == "fills" for snap in result.snapshots)
