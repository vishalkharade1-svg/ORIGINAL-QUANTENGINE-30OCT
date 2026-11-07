import pytest
from research.economics.delta_ws_friction_capture import DeltaOrderbookState


def snapshot(seq=10, ts=1_000_000):
    return {"type":"ob_updates","action":"snapshot","sy":"BTCUSD","seq":seq,"ts":ts,
            "b":[["100","5"],["99","3"]],"a":[["101","4"],["102","2"]]}


def test_snapshot_then_contiguous_update_emits_top_of_book():
    b = DeltaOrderbookState("BTCUSD")
    o1 = b.apply(snapshot())
    o2 = b.apply({"type":"ob_updates","action":"update","sy":"BTCUSD","seq":11,"ts":1_001_000,
                  "b":[["100","0"],["100.5","2"]],"a":[]})
    assert o1.best_bid == "100" and o1.best_ask == "101"
    assert o2.best_bid == "100.5" and o2.best_ask == "101"
    assert o2.to_sample()["timestamp_ms"] == 1001


def test_sequence_gap_invalidates_state():
    b = DeltaOrderbookState("BTCUSD"); b.apply(snapshot())
    with pytest.raises(ValueError, match="sequence gap"):
        b.apply({"type":"ob_updates","action":"update","sy":"BTCUSD","seq":12,"ts":1_002_000,
                 "b":[],"a":[]})
    assert not b.ready


def test_update_before_snapshot_rejected():
    b = DeltaOrderbookState("BTCUSD")
    with pytest.raises(ValueError, match="before snapshot"):
        b.apply({"type":"ob_updates","action":"update","sy":"BTCUSD","seq":1,"ts":1,
                 "b":[],"a":[]})


def test_crossed_book_rejected():
    b = DeltaOrderbookState("BTCUSD")
    with pytest.raises(ValueError, match="crossed"):
        b.apply({"type":"ob_updates","action":"snapshot","sy":"BTCUSD","seq":1,"ts":1,
                 "b":[["101","1"]],"a":[["101","2"]]})


def test_wrong_symbol_rejected():
    b = DeltaOrderbookState("BTCUSD")
    m = snapshot(); m["sy"] = "ETHUSD"
    with pytest.raises(ValueError, match="symbol"):
        b.apply(m)


def test_error_message_resets_book():
    b = DeltaOrderbookState("BTCUSD"); b.apply(snapshot())
    with pytest.raises(ValueError, match="error message"):
        b.apply({"type":"ob_updates","action":"error","sy":"BTCUSD"})
    assert not b.ready
