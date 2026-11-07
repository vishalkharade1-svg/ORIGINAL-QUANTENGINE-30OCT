import pytest
from research.economics.delta_fill_evidence import (
    build_artifact, load_and_verify, normalize_fills, capture_authenticated_fills,
)


def row(i=1, ts=1000):
    return {"id": f"fill-{i}", "order_id": "order-1", "symbol": "BTCUSD",
            "side": "buy", "role": "taker", "size": "2", "price": "100.5",
            "commission": "0.10", "created_at": ts}


def test_normalization_and_fingerprint_roundtrip(tmp_path):
    a = build_artifact(fills=[row()], symbol="BTCUSD", captured_at="2026-10-08T00:00:00Z",
                       request_params={"symbol":"BTCUSD"}, source_endpoint="https://api.india.delta.exchange/v2/fills")
    p = tmp_path / "fills.json"
    from research.economics.delta_fill_evidence import write_artifact
    write_artifact(a, p)
    b = load_and_verify(p)
    assert b.evidence_sha256 == a.evidence_sha256
    assert b.fills[0]["fill_id"] == "fill-1"


def test_duplicate_or_bad_fill_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        normalize_fills([row(1), row(1, 1001)], symbol="BTCUSD")
    with pytest.raises(ValueError, match="role"):
        normalize_fills([dict(row(), role="unknown")], symbol="BTCUSD")


def test_non_real_cannot_be_promoted():
    with pytest.raises(ValueError, match="REAL"):
        build_artifact(fills=[row()], symbol="BTCUSD", captured_at="x", request_params={},
                       source_endpoint="x", provenance_status="FIXTURE")


def test_tamper_detected(tmp_path):
    from research.economics.delta_fill_evidence import write_artifact
    a = build_artifact(fills=[row()], symbol="BTCUSD", captured_at="x", request_params={}, source_endpoint="x")
    p = tmp_path / "fills.json"
    write_artifact(a, p)
    raw = p.read_text().replace('"price": "100.5"', '"price": "100.6"')
    p.write_text(raw)
    with pytest.raises(ValueError, match="fingerprint"):
        load_and_verify(p)


def test_authenticated_client_is_required():
    class Fake:
        authenticated = False
    with pytest.raises(RuntimeError, match="authenticated"):
        capture_authenticated_fills(Fake(), symbol="BTCUSD", source_endpoint="x", captured_at="x")


def test_authenticated_response_only_source():
    class Fake:
        authenticated = True
        def get(self, path, params=None):
            assert path == "/v2/fills"
            return {"success": True, "result": [row()]}
    a = capture_authenticated_fills(Fake(), symbol="BTCUSD", source_endpoint="x", captured_at="x")
    assert a.provenance_status == "REAL"
    assert a.fills[0]["fill_id"] == "fill-1"


def test_fill_binds_to_real_friction():
    from research.economics.market_friction_evidence import build_artifact as build_friction
    from research.economics.delta_fill_evidence import bind_to_market_friction
    f = build_artifact(fills=[row(ts=1000)], symbol="BTCUSD", captured_at="x", request_params={}, source_endpoint="x")
    m = build_friction(samples=[{"symbol":"BTCUSD","timestamp_ms":1000,"best_bid":"100","best_ask":"101"}],
                       symbol="BTCUSD", captured_at="x", source_endpoint="x", provenance_status="REAL")
    b = bind_to_market_friction(f, m)
    assert b["bindings"][0]["reference_price"] == "101"
    assert b["bindings"][0]["slippage"] == "-0.5"


def test_fill_binding_requires_time_alignment():
    from research.economics.market_friction_evidence import build_artifact as build_friction
    from research.economics.delta_fill_evidence import bind_to_market_friction
    f = build_artifact(fills=[row(ts=1000)], symbol="BTCUSD", captured_at="x", request_params={}, source_endpoint="x")
    m = build_friction(samples=[{"symbol":"BTCUSD","timestamp_ms":5000,"best_bid":"100","best_ask":"101"}],
                       symbol="BTCUSD", captured_at="x", source_endpoint="x", alignment_ms=100)
    with pytest.raises(ValueError, match="aligned"):
        bind_to_market_friction(f, m)


def venue_row(i=1, symbol="BTCUSD", created_at="2026-10-11T08:13:04.391968Z"):
    return {"id": f"venue-fill-{i}", "order_id": "2175077531",
            "product_symbol": symbol, "side": "sell", "role": "taker",
            "size": "20", "price": "4186.64", "commission": "0.00889244",
            "created_at": created_at, "fill_type": "normal",
            "product_id": 169532}


def test_product_symbol_accepted_as_venue_symbol():
    fills = normalize_fills([venue_row()], symbol="BTCUSD")
    assert fills[0]["symbol"] == "BTCUSD"
    assert fills[0]["fill_id"] == "venue-fill-1"
    with pytest.raises(ValueError, match="symbol mismatch"):
        normalize_fills([venue_row(symbol="ETHUSD")], symbol="BTCUSD")


def test_iso_timestamp_parses_to_epoch_ms():
    fills = normalize_fills(
        [venue_row(created_at="2026-10-11T08:13:04.391968Z")],
        symbol="BTCUSD")
    from datetime import datetime, timezone
    expected = int(datetime(2026, 10, 11, 8, 13, 4, 391968,
                            tzinfo=timezone.utc).timestamp() * 1000)
    assert fills[0]["timestamp"] == expected
    # Legacy integer epochs pass through unchanged.
    assert normalize_fills([row(ts=1000)], symbol="BTCUSD")[0]["timestamp"] == 1000
    with pytest.raises(ValueError, match="invalid"):
        normalize_fills([dict(row(), created_at="not-a-time")],
                        symbol="BTCUSD")


def test_capture_filters_ignored_symbol_param_and_sorts():
    class Fake:
        authenticated = True

        def get(self, path, params=None):
            assert params.get("symbol") == "BTCUSD"
            return {"success": True, "result": [
                venue_row(2, created_at="2026-10-11T08:14:00Z"),
                dict(venue_row(9, symbol="ETHUSD"),
                     created_at="2026-10-11T08:15:00Z"),
                venue_row(1, created_at="2026-10-11T08:13:00Z"),
            ]}
    a = capture_authenticated_fills(Fake(), symbol="BTCUSD",
                                    source_endpoint="x", captured_at="x",
                                    request_params={"symbol": "BTCUSD",
                                                    "page_size": 100})
    assert [f["fill_id"] for f in a.fills] == ["venue-fill-1",
                                              "venue-fill-2"]
    assert a.request_params["symbol_rows_seen"] == 3
    assert a.request_params["symbol_rows_kept"] == 2


def test_capture_empty_after_symbol_filter_is_empty_not_success():
    class Fake:
        authenticated = True

        def get(self, path, params=None):
            return {"success": True, "result": [venue_row(9, symbol="ETHUSD")]}
    with pytest.raises(ValueError, match="non-empty"):
        capture_authenticated_fills(Fake(), symbol="BTCUSD",
                                    source_endpoint="x", captured_at="x",
                                    request_params={})
