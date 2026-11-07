import asyncio
import hashlib
import hmac
import json
import pytest

from research.economics.delta_fill_evidence import build_artifact
from research.economics.delta_private_fill_capture import (
    PRIVATE_WS_PRODUCTION, archive_hash, capture_from_frames, key_auth_message,
    normalize_ws_fill, reconcile_with_rest, subscription,
)


def frame(seq=1, fill="f1", order="o1", price="100", ts=1700000000000000):
    return {"type":"v2/user_trades","sy":"BTCUSD","f":fill,"R":"normal","u":1,"o":order,
            "S":"buy","s":2,"p":price,"po":2,"r":"taker","timestamp":ts,"seq_no":seq}


def test_key_auth_signature_is_exact():
    msg = key_auth_message("key", "secret", timestamp=123)
    assert msg["payload"]["timestamp"] == 123
    assert msg["payload"]["signature"] == hmac.new(b"secret", b"GET123/live", hashlib.sha256).hexdigest()


def test_subscription_is_explicit_symbol():
    assert subscription("BTCUSD")["payload"]["channels"][0]["symbols"] == ["BTCUSD"]


def test_capture_requires_contiguous_sequences():
    cap = capture_from_frames([frame(1), frame(2, "f2", "o2", "101")], symbol="BTCUSD")
    assert cap.first_seq == 1 and cap.last_seq == 2
    with pytest.raises(ValueError, match="sequence gap"):
        capture_from_frames([frame(1), frame(3, "f3", "o3")], symbol="BTCUSD")


def test_auth_failure_rejected():
    with pytest.raises(RuntimeError):
        capture_from_frames([{"type":"key-auth","success":False}], symbol="BTCUSD")


def test_duplicate_fill_rejected():
    with pytest.raises(ValueError, match="duplicate websocket"):
        capture_from_frames([frame(1), frame(2, "f1", "o2")], symbol="BTCUSD")


def test_rest_reconciliation_matches():
    cap = capture_from_frames([frame(1)], symbol="BTCUSD")
    rest = build_artifact(fills=[{"id":"f1","order_id":"o1","symbol":"BTCUSD","side":"buy","role":"taker","size":2,"price":"100","commission":"0.1","created_at":1700000000000000}], symbol="BTCUSD", captured_at="2026-10-08T00:00:00Z", request_params={"symbol":"BTCUSD"}, source_endpoint="https://api.india.delta.exchange/v2/fills")
    result = reconcile_with_rest(cap, rest)
    assert result["status"] == "MATCHED" and result["fill_count"] == 1


def test_rest_reconciliation_rejects_missing_fill():
    cap = capture_from_frames([frame(1)], symbol="BTCUSD")
    rest = build_artifact(fills=[{"id":"other","order_id":"o1","symbol":"BTCUSD","side":"buy","role":"taker","size":2,"price":"100","commission":"0.1","created_at":1700000000000000}], symbol="BTCUSD", captured_at="2026-10-08T00:00:00Z", request_params={}, source_endpoint="https://api.india.delta.exchange/v2/fills")
    with pytest.raises(ValueError):
        reconcile_with_rest(cap, rest)


def test_archive_hash_changes_on_frame_mutation():
    a = archive_hash([frame(1)])
    b = archive_hash([dict(frame(1), p="101")])
    assert a != b


def test_production_endpoint_is_private():
    assert PRIVATE_WS_PRODUCTION.startswith("wss://socket.")

from research.economics.delta_private_fill_capture import build_private_archive, verify_private_archive

def test_private_archive_roundtrip_and_tamper_detection():
    cap = capture_from_frames([frame(1), frame(2, "f2", "o2", "101")], symbol="BTCUSD")
    archive = build_private_archive(cap)
    restored = verify_private_archive(archive)
    assert restored.last_seq == 2
    archive["frames"][0]["frame"]["p"] = "999"
    with pytest.raises(ValueError):
        verify_private_archive(archive)


def real_frame(fill="f1", order="o1", ts=1791709221848602, **kw):
    base = {"type": "v2/user_trades", "sy": "BTCUSD", "f": fill,
            "R": "normal", "u": 12141396, "o": order, "S": "buy",
            "s": "1", "p": "83019", "po": 1, "r": "taker",
            "t": ts, "i": 84, "se": 5}
    base.update(kw)
    return base


def test_real_venue_schema_microsecond_t_no_seq():
    from research.economics.delta_private_fill_capture import (
        build_private_archive, verify_private_archive)
    cap = capture_from_frames(
        [real_frame("f1", "o1", 1791709221848602),
         real_frame("f2", "o2", 1791709221900000)], symbol="BTCUSD")
    assert cap.first_seq is None and cap.last_seq is None
    assert [f["timestamp"] for f in cap.fills] == [1791709221848602,
                                                  1791709221900000]
    assert cap.fills[0]["client_order_id"] == ""
    archive = build_private_archive(cap)
    restored = verify_private_archive(archive)
    assert restored.first_seq is None
    assert len(restored.fills) == 2


def test_real_schema_client_order_id_preserved():
    from research.economics.delta_private_fill_capture import (
        normalize_ws_fill)
    fill = normalize_ws_fill(real_frame(c="QE-exp-ID-R1"))
    assert fill["client_order_id"] == "QE-exp-ID-R1"


def test_real_schema_out_of_order_rejected():
    with pytest.raises(ValueError, match="timestamp order"):
        capture_from_frames(
            [real_frame("f1", "o1", 1791709221900000),
             real_frame("f2", "o2", 1791709221848602)], symbol="BTCUSD")
