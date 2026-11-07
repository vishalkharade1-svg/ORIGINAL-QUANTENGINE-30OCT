"""Phase 96: /health must reflect feed staleness (no healthy-on-dead-data).

_feed_health() folds 6D subscription states into a deterministic verdict:
fresh only when >=1 subscription is tracked and none is STALE/FAILED.
Additive data_feed block on the health snapshot; existing keys untouched.
"""
from core.monitoring.api_server import (
    _feed_health,
    _feed_state_of,
    _health_snapshot,
)


class _FakeSubs:
    def __init__(self, states):
        self._states = dict(states)

    def statuses(self):
        return dict(self._states)


class _FakeEngine:
    def __init__(self, states):
        self.subscriptions = _FakeSubs(states)


def test_feed_health_fresh_only_when_live():
    assert _feed_health(_FakeEngine({}))["fresh"] is False
    assert _feed_health(_FakeEngine({}))["reason"] == "no_subscriptions"
    healthy = _feed_health(_FakeEngine({"BTC": "LIVE", "ETH": "CONNECTING"}))
    assert healthy["fresh"] is True
    assert healthy["tracked"] == 2
    stale = _feed_health(_FakeEngine({"BTC": "LIVE", "ETH": "STALE"}))
    assert stale["fresh"] is False
    assert stale["degraded"] == {"ETH": "STALE"}
    failed = _feed_health(_FakeEngine({"BTC": "FAILED"}))
    assert failed["fresh"] is False
    assert failed["reason"] == "stale_or_failed_feeds"


def test_feed_health_tolerates_state_shapes():
    assert _feed_state_of(None) == "UNKNOWN"
    assert _feed_state_of("stale") == "STALE"
    assert _feed_state_of({"status": "failed"}) == "FAILED"

    class S:
        status = "LIVE"

    assert _feed_state_of(S()) == "LIVE"
    assert _feed_health(object())["reason"] == "no_subscriptions"


def test_health_snapshot_carries_feed_verdict():
    class Life:
        def health(self):
            return {"lifecycle_state": "RUNNING"}

    snap = _health_snapshot(_FakeEngine({"BTC": "STALE"}), Life())
    assert snap["lifecycle_state"] == "RUNNING"
    assert snap["data_feed"]["fresh"] is False
    assert snap["data_feed"]["degraded"] == {"BTC": "STALE"}
