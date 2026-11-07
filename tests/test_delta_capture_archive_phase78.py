import json
import pytest

from research.economics.delta_capture_archive import build_archive, load_and_verify, write_archive
from research.economics.market_friction_capture import CaptureIdentity


def ident():
    return CaptureIdentity("delta", "PRODUCTION", "BTCUSD", "wss://public-socket.delta.exchange", "LIVE_CAPTURE", "p78")


def frames():
    return [
        {"type": "ob_updates", "action": "snapshot", "sy": "BTCUSD", "seq": 10, "ts": 1000000,
         "b": [["100", "5"]], "a": [["101", "4"]]},
        {"type": "ob_updates", "action": "update", "sy": "BTCUSD", "seq": 11, "ts": 1001000,
         "b": [["100", "4"]], "a": []},
    ]


def test_archive_roundtrip_and_chain(tmp_path):
    a = build_archive(ident(), frames())
    p = tmp_path / "capture.json"
    write_archive(a, p)
    b = load_and_verify(p)
    assert b.final_chain_hash == a.final_chain_hash
    assert b.frame_hashes == a.frame_hashes


def test_archive_detects_frame_tamper(tmp_path):
    a = build_archive(ident(), frames())
    p = tmp_path / "capture.json"
    write_archive(a, p)
    raw = json.loads(p.read_text())
    raw["frames"][1]["b"][0][1] = "999"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="integrity verification failed"):
        load_and_verify(p)


def test_archive_requires_live_capture_identity():
    bad = CaptureIdentity("delta", "PRODUCTION", "BTCUSD", "fixture", "FIXTURE", "p78")
    with pytest.raises(ValueError, match="LIVE_CAPTURE"):
        build_archive(bad, frames())


def test_archive_empty_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        build_archive(ident(), [])


def test_archive_binds_exactly_to_artifact():
    from research.economics.delta_capture_archive import verify_archive_matches_artifact
    from research.economics.market_friction_evidence import build_artifact
    fs = frames()
    a = build_archive(ident(), fs)
    artifact = build_artifact(
        samples=[
            {"symbol":"BTCUSD", "timestamp_ms":1000, "best_bid":"100", "best_ask":"101"},
            {"symbol":"BTCUSD", "timestamp_ms":1001, "best_bid":"100", "best_ask":"101"},
        ], symbol="BTCUSD", captured_at="x", source_endpoint=ident().source_endpoint,
        venue="delta", alignment_ms=1000, provenance_status="REAL")
    verify_archive_matches_artifact(a, artifact)


def test_archive_artifact_binding_rejects_price_mutation():
    from research.economics.delta_capture_archive import verify_archive_matches_artifact
    from research.economics.market_friction_evidence import build_artifact
    a = build_archive(ident(), frames())
    artifact = build_artifact(
        samples=[
            {"symbol":"BTCUSD", "timestamp_ms":1000, "best_bid":"100", "best_ask":"101"},
            {"symbol":"BTCUSD", "timestamp_ms":1001, "best_bid":"99", "best_ask":"101"},
        ], symbol="BTCUSD", captured_at="x", source_endpoint=ident().source_endpoint,
        venue="delta", alignment_ms=1000, provenance_status="REAL")
    with pytest.raises(ValueError, match="observation mismatch"):
        verify_archive_matches_artifact(a, artifact)
