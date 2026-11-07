import json
import pytest
from research.economics.fee_evidence import (
    build_artifact, load_and_verify, normalize_product_fee, to_cost_spec, write_artifact,
)


def sample():
    return {"success": True, "result": [{
        "symbol": "BTCUSD",
        "maker_commission_rate": "0.0002",
        "taker_commission_rate": "0.0005",
    }]}


def test_fee_normalization_and_cost_spec_provenance():
    a = build_artifact(response=sample(), symbol="BTCUSD", captured_at="2026-10-07T12:00:00Z")
    spec = to_cost_spec(a, role="taker")
    assert spec.rate == pytest.approx(0.0005)
    assert spec.venue_source.startswith("delta:/v2/products#")


def test_fee_artifact_tamper_rejected(tmp_path):
    a = build_artifact(response=sample(), symbol="BTCUSD", captured_at="2026-10-07T12:00:00Z")
    p = tmp_path / "fee.json"
    write_artifact(a, p)
    raw = json.loads(p.read_text())
    raw["result"]["taker_commission_rate"] = "0.0009"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="fingerprint mismatch|normalization mismatch"):
        load_and_verify(p)


def test_fixture_fee_cannot_be_promoted(tmp_path):
    a = build_artifact(response=sample(), symbol="BTCUSD", captured_at="2026-10-07T12:00:00Z")
    raw = a.to_dict(); raw["provenance_status"] = "FIXTURE"
    p = tmp_path / "fixture.json"; p.write_text(json.dumps(raw))
    loaded = load_and_verify(p)
    with pytest.raises(ValueError, match="genuine venue"):
        to_cost_spec(loaded, role="maker")


def test_missing_role_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        normalize_product_fee({"result": []}, symbol="BTCUSD")
