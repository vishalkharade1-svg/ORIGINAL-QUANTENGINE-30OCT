from pathlib import Path
import json
import pytest

from research.economics.market_friction_capture import (
    CaptureIdentity, MarketFrictionCapture, capture_manifest, write_capture_manifest,
)
from research.economics.market_friction_evidence import load_and_verify


def identity():
    return CaptureIdentity(
        venue="delta", environment="PRODUCTION", symbol="BTCUSD",
        source_endpoint="wss://public-socket.delta.exchange",
        transport="LIVE_CAPTURE", capture_id="cap-001",
    )


def test_live_capture_requires_real_transport_identity():
    with pytest.raises(ValueError, match="LIVE_CAPTURE"):
        CaptureIdentity("delta", "PRODUCTION", "BTCUSD", "ws", "FIXTURE", "x").validate()


def test_capture_rejects_nonmonotonic_and_writes_real_artifact(tmp_path: Path):
    c = MarketFrictionCapture(identity(), alignment_ms=10)
    c.add(timestamp_ms=1000, best_bid="100", best_ask="101",
          fill={"timestamp_ms": 1001, "side": "buy", "price": "101.1"})
    with pytest.raises(ValueError, match="ascending"):
        c.add(timestamp_ms=1000, best_bid="100", best_ask="101")
    c.add(timestamp_ms=2000, best_bid="101", best_ask="102")
    p = tmp_path / "friction.json"
    artifact = c.write(p, captured_at="2026-10-07T00:00:00Z")
    assert artifact.provenance_status == "REAL"
    assert load_and_verify(p).evidence_sha256 == artifact.evidence_sha256


def test_empty_capture_cannot_be_finalized():
    c = MarketFrictionCapture(identity())
    with pytest.raises(ValueError, match="empty"):
        c.finalize()


def test_capture_manifest_binds_identity_and_hash(tmp_path: Path):
    c = MarketFrictionCapture(identity())
    c.add(timestamp_ms=1000, best_bid="100", best_ask="101")
    artifact = c.finalize(captured_at="2026-10-07T00:00:00Z")
    manifest = capture_manifest(artifact, identity())
    assert manifest["capture_id"] == "cap-001"
    assert manifest["evidence_sha256"] == artifact.evidence_sha256
    p = tmp_path / "manifest.json"
    write_capture_manifest(manifest, p)
    assert json.loads(p.read_text())["sample_count"] == 1


def test_sandbox_requires_explicit_sandbox_identity():
    with pytest.raises(ValueError):
        CaptureIdentity("delta", "UNKNOWN", "BTCUSD", "wss://x", "LIVE_CAPTURE", "x").validate()
