from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.research.expiry_squeeze.recorder import (
    CaptureLimitError,
    CorruptJournalError,
    ExpirySqueezeRecorder,
    RecorderError,
    candidate_identity,
)


INSTRUMENT = {
    "exchange": "BSE",
    "underlying": "SENSEX",
    "instrument_type": "OPTION",
    "expiry": "2026-11-12",
    "strike": "71400",
    "option_type": "PE",
    "symbol": "SENSEX26NOV1271400PE",
}


def test_append_verifies_hash_chain_and_survives_restart(tmp_path):
    path = tmp_path / "session.jsonl"
    first = ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")
    a = first.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00+05:30",
                     instrument=INSTRUMENT, payload={"bid": "8.80", "ask": "8.90"},
                     received_timestamp="2026-11-12T03:45:00Z")
    b = first.append("OPTION_TRADE", exchange_timestamp="2026-11-12T09:15:01+05:30",
                     instrument=INSTRUMENT, payload={"price": "8.90", "quantity": 25})
    assert a["sequence"] == 1
    assert b["sequence"] == 2
    restarted = ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")
    assert restarted.event_count == 2
    assert restarted.last_event_hash == b["event_hash"]
    assert ExpirySqueezeRecorder.verify_journal(path, "SENSEX-2026-11-12")["status"] == "VERIFIED"


def test_candidate_rejections_are_persisted_and_never_authorize_action(tmp_path):
    recorder = ExpirySqueezeRecorder(tmp_path / "session.jsonl", "SENSEX-2026-11-12")
    event = recorder.record_candidate(
        decision_timestamp="2026-11-12T09:16:00+05:30",
        instrument=INSTRUMENT,
        instrument_id="BSE:SENSEX:2026-11-12:71400:PE",
        state="REJECTED", premium="8.90",
        reasons=("SPREAD_TOO_WIDE", "INDEX_CONFIRMATION_MISSING"),
        features={"spread_pct": "0.12", "volume_ratio": "0.7"},
    )
    assert event["payload"]["candidate_state"] == "REJECTED"
    assert event["payload"]["action_authorized"] is False
    assert event["payload"]["rejection_reasons"] == ["SPREAD_TOO_WIDE", "INDEX_CONFIRMATION_MISSING"]


def test_candidate_identity_is_timezone_normalized_and_stable():
    a = candidate_identity("SENSEX-2026-11-12", "BSE:SENSEX:71400:PE", "2026-11-12T09:15:00+05:30")
    b = candidate_identity("SENSEX-2026-11-12", "BSE:SENSEX:71400:PE", "2026-11-12T03:45:00Z")
    assert a == b


def test_rejects_naive_timestamps_and_non_json_nan(tmp_path):
    recorder = ExpirySqueezeRecorder(tmp_path / "session.jsonl", "SENSEX-2026-11-12")
    with pytest.raises(RecorderError, match="include a timezone"):
        recorder.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00",
                        instrument=INSTRUMENT, payload={"bid": "8.8"})
    with pytest.raises(RecorderError, match="strict JSON"):
        recorder.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                        instrument=INSTRUMENT, payload={"bid": float("nan")})
    assert recorder.event_count == 0


def test_rejects_corrupted_hash_chain(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")
    recorder.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                    instrument=INSTRUMENT, payload={"bid": "8.8"})
    row = json.loads(path.read_text().strip())
    row["payload"]["bid"] = "99.0"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(CorruptJournalError, match="checksum mismatch"):
        ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")


def test_truncated_tail_fails_closed(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")
    recorder.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                    instrument=INSTRUMENT, payload={"bid": "8.8"})
    with path.open("ab") as stream:
        stream.write(b'{"partial":')
    with pytest.raises(CorruptJournalError, match="truncated"):
        ExpirySqueezeRecorder(path, "SENSEX-2026-11-12")


def test_event_and_byte_budgets_are_hard_limits(tmp_path):
    event_limited = ExpirySqueezeRecorder(tmp_path / "events.jsonl", "SENSEX-2026-11-12", max_events=1)
    event_limited.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                         instrument=INSTRUMENT, payload={"bid": "8.8"})
    with pytest.raises(CaptureLimitError, match="MAX_EVENTS_REACHED"):
        event_limited.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:01Z",
                             instrument=INSTRUMENT, payload={"bid": "8.9"})
    byte_limited = ExpirySqueezeRecorder(tmp_path / "bytes.jsonl", "SENSEX-2026-11-12", max_bytes=10)
    with pytest.raises(CaptureLimitError, match="MAX_BYTES_REACHED"):
        byte_limited.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                            instrument=INSTRUMENT, payload={"bid": "8.8"})


def test_closed_recorder_rejects_writes(tmp_path):
    recorder = ExpirySqueezeRecorder(tmp_path / "session.jsonl", "SENSEX-2026-11-12")
    recorder.close()
    with pytest.raises(RecorderError, match="closed"):
        recorder.append("OPTION_QUOTE", exchange_timestamp="2026-11-12T09:15:00Z",
                        instrument=INSTRUMENT, payload={"bid": "8.8"})
