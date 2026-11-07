import hashlib
import json
import pytest

from research.economics.orderbook_evidence import (
    build_artifact, load_and_verify, normalize_orderbook, write_artifact,
)


def sample():
    return {"success": True, "result": {
        "symbol": "BTCUSD", "last_updated_at": 1700000000000000,
        "buy": [{"price": "100", "size": 5}, {"price": "99", "size": 10}],
        "sell": [{"price": "101", "size": 7}, {"price": "102", "size": 11}],
    }}


def test_orderbook_normalization_calculates_spread_without_claiming_slippage():
    r = normalize_orderbook(sample(), symbol="BTCUSD")
    assert r["best_bid"] == "100"
    assert r["best_ask"] == "101"
    assert float(r["spread_bps"]) == pytest.approx(99.50248756)
    assert "realized_slippage" not in r


def test_orderbook_rejects_crossed_and_unsorted_books():
    bad = sample()
    bad["result"]["sell"][0]["price"] = "99"
    with pytest.raises(ValueError, match="crossed"):
        normalize_orderbook(bad, symbol="BTCUSD")
    bad2 = sample()
    bad2["result"]["buy"][1]["price"] = "101"
    with pytest.raises(ValueError, match="strictly sorted"):
        normalize_orderbook(bad2, symbol="BTCUSD")


def test_orderbook_artifact_fingerprint_detects_tamper(tmp_path):
    artifact = build_artifact(response=sample(), symbol="BTCUSD", captured_at="2026-10-07T12:00:00Z")
    path = tmp_path / "ob.json"
    write_artifact(artifact, path)
    loaded = load_and_verify(path)
    assert loaded.evidence_sha256 == artifact.evidence_sha256
    raw = json.loads(path.read_text())
    raw["result"]["best_ask"] = "101.5"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="normalization mismatch|fingerprint mismatch"):
        load_and_verify(path)


def test_delta_history_orderbook_strict_adapter(monkeypatch):
    from core.exchanges.delta.delta_history import DeltaHistory
    history = DeltaHistory()
    monkeypatch.setattr(history.rest, "get", lambda endpoint, params=None: sample())
    evidence = history.orderbook_evidence("BTCUSD", depth=2)
    assert evidence["result"]["spread"] == "1"
    assert evidence["request"]["depth"] == 2
    assert len(evidence["sha256"]) == 64
