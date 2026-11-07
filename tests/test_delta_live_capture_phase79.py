import pytest

from research.economics.delta_live_capture import process_frames, subscription, decode_frame
from research.economics.market_friction_capture import CaptureIdentity


def ident():
    return CaptureIdentity("delta", "PRODUCTION", "BTCUSD", "wss://public-socket.india.delta.exchange", "LIVE_CAPTURE", "p79-test")


def frames():
    return [
        {"type":"ob_updates","action":"snapshot","sy":"BTCUSD","seq":100,"ts":1_000_000,
         "a":[["101","2"]],"b":[["99","3"]]},
        {"type":"ob_updates","action":"update","sy":"BTCUSD","seq":101,"ts":1_001_000,
         "a":[["101","1"]],"b":[]},
        {"type":"ob_updates","action":"update","sy":"BTCUSD","seq":102,"ts":1_002_000,
         "a":[],"b":[["100","4"]]},
    ]


def test_subscription_is_explicit_symbol():
    assert subscription("BTCUSD")["payload"]["channels"][0]["name"] == "ob_updates"
    with pytest.raises(ValueError):
        subscription("all")


def test_process_frames_binds_archive_to_artifact():
    artifact, archive, manifest = process_frames(frames(), identity=ident(), min_observations=2)
    assert artifact.provenance_status == "REAL"
    assert len(archive.frames) == 3
    assert manifest["first_sequence"] == 100
    assert manifest["last_sequence"] == 102


def test_sequence_gap_fails_closed():
    bad = frames()
    bad[2] = dict(bad[2], seq=103)
    with pytest.raises(ValueError, match="sequence"):
        process_frames(bad, identity=ident(), min_observations=2)


def test_provider_error_fails_closed():
    bad = frames()[:1] + [{"type":"ob_updates","action":"error","sy":"BTCUSD","msg":"failed"}]
    with pytest.raises(ValueError, match="Delta orderbook error"):
        process_frames(bad, identity=ident(), min_observations=2)


def test_insufficient_observations_fails():
    with pytest.raises(ValueError, match="insufficient"):
        process_frames(frames()[:1], identity=ident(), min_observations=2)


def test_decode_requires_json_object():
    assert decode_frame('{"type":"heartbeat"}') ["type"] == "heartbeat"
    with pytest.raises(ValueError):
        decode_frame('[]')
