from pathlib import Path
import json
import pytest

from research.economics.market_friction_evidence import build_artifact, load_and_verify


def samples():
    return [
        {"symbol": "BTCUSD", "timestamp_ms": 1000, "best_bid": "100", "best_ask": "101",
         "fill": {"timestamp_ms": 1001, "side": "buy", "price": "101.2"}},
        {"symbol": "BTCUSD", "timestamp_ms": 2000, "best_bid": "101", "best_ask": "102",
         "fill": {"timestamp_ms": 2001, "side": "sell", "price": "100.8"}},
    ]


def test_time_aligned_friction_and_realized_slippage_are_distinct():
    a = build_artifact(samples=samples(), symbol="BTCUSD", captured_at="2026-10-07T00:00:00Z",
                       source_endpoint="/v2/l2orderbook/BTCUSD", alignment_ms=10)
    assert a.has_realized_fill_evidence
    assert a.samples[0]["spread"] == "1"
    assert a.samples[0]["fill"]["slippage"] == "0.2"
    assert a.samples[1]["fill"]["slippage"] == "0.2"


def test_unaligned_fill_is_rejected():
    bad = samples()
    bad[0]["fill"]["timestamp_ms"] = 5000
    with pytest.raises(ValueError, match="alignment"):
        build_artifact(samples=bad, symbol="BTCUSD", captured_at="x",
                       source_endpoint="/v2/l2orderbook/BTCUSD", alignment_ms=10)


def test_trade_tape_without_book_is_rejected():
    bad = [{"symbol": "BTCUSD", "timestamp_ms": 1000, "price": "100", "quantity": "1"}]
    with pytest.raises(ValueError):
        build_artifact(samples=bad, symbol="BTCUSD", captured_at="x", source_endpoint="trades")


def test_nonmonotonic_samples_are_rejected():
    bad = list(reversed(samples()))
    with pytest.raises(ValueError, match="ascending"):
        build_artifact(samples=bad, symbol="BTCUSD", captured_at="x",
                       source_endpoint="/v2/l2orderbook/BTCUSD")


def test_artifact_roundtrip_and_tamper_detection(tmp_path: Path):
    a = build_artifact(samples=samples(), symbol="BTCUSD", captured_at="x",
                       source_endpoint="/v2/l2orderbook/BTCUSD", alignment_ms=10)
    p = tmp_path / "friction.json"
    from research.economics.market_friction_evidence import write_artifact
    write_artifact(a, p)
    assert load_and_verify(p).evidence_sha256 == a.evidence_sha256
    raw = json.loads(p.read_text())
    raw["samples"][0]["best_ask"] = "103"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="fingerprint|normalization"):
        load_and_verify(p)


def test_fixture_provenance_cannot_become_real_by_loading():
    a = build_artifact(samples=samples(), symbol="BTCUSD", captured_at="x",
                       source_endpoint="/fixture", provenance_status="FIXTURE")
    assert a.provenance_status == "FIXTURE"
