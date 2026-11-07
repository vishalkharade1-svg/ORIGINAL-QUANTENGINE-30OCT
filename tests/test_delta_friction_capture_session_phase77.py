import pytest

from research.economics.delta_friction_capture_session import DeltaFrictionCaptureSession
from research.economics.market_friction_capture import CaptureIdentity


def ident():
    return CaptureIdentity(
        venue="delta", environment="PRODUCTION", symbol="BTCUSD",
        source_endpoint="wss://public-socket.delta.exchange",
        transport="LIVE_CAPTURE", capture_id="phase77-001",
    )


def snap(seq=10, ts=1_000_000):
    return {"type":"ob_updates", "action":"snapshot", "sy":"BTCUSD",
            "seq":seq, "ts":ts, "b":[["100","5"]], "a":[["101","4"]]}


def upd(seq, ts, bid="100"):
    return {"type":"ob_updates", "action":"update", "sy":"BTCUSD",
            "seq":seq, "ts":ts, "b":[[bid,"2"]], "a":[]}


def test_session_binds_contiguous_frames_to_capture():
    s = DeltaFrictionCaptureSession(ident(), alignment_ms=10)
    s.ingest(snap())
    s.ingest(upd(11, 1_001_000, "100.5"))
    a = s.finalize(captured_at="2026-10-07T00:00:00Z")
    assert a.provenance_status == "REAL"
    assert len(a.samples) == 2
    assert s.stats.first_sequence == 10
    assert s.stats.last_sequence == 11
    assert s.stats.continuity_failures == 0


def test_sequence_gap_invalidates_entire_session():
    s = DeltaFrictionCaptureSession(ident())
    s.ingest(snap())
    with pytest.raises(ValueError, match="sequence gap"):
        s.ingest(upd(12, 1_002_000))
    assert s.invalid
    assert s.stats.continuity_failures == 1
    with pytest.raises(RuntimeError, match="cannot be finalized"):
        s.finalize()


def test_pre_snapshot_failure_cannot_be_recovered_inside_session():
    s = DeltaFrictionCaptureSession(ident())
    with pytest.raises(ValueError, match="before snapshot"):
        s.ingest(upd(1, 1_000_000))
    with pytest.raises(RuntimeError, match="fresh capture"):
        s.ingest(snap())


def test_empty_session_cannot_finalize():
    s = DeltaFrictionCaptureSession(ident())
    with pytest.raises(ValueError, match="no orderbook observations"):
        s.finalize()


def test_fixture_transport_is_still_rejected():
    with pytest.raises(ValueError, match="LIVE_CAPTURE"):
        CaptureIdentity("delta", "PRODUCTION", "BTCUSD", "fixture", "FIXTURE", "x").validate()
