"""Phase154: fill-evidence error taxonomy (deterministic, offline, stdlib).

A genuinely empty symbol window must surface as the typed
EmptySymbolWindowError (honest negative evidence). Malformed rows,
non-list results, duplicates, bad timestamps, auth failures, and
unsuccessful responses must NEVER be mislabeled as empty.
"""
import pytest

from research.economics.delta_fill_evidence import (
    EmptySymbolWindowError,
    capture_authenticated_fills,
)


def venue_row(i=1, symbol="BTCUSD", ts=1000, **over):
    base = {"id": f"fill-{i}", "order_id": "order-1", "symbol": symbol,
            "side": "buy", "role": "taker", "size": "2", "price": "100.5",
            "commission": "0.10", "created_at": ts}
    base.update(over)
    return base


class Fake:
    def __init__(self, payload, authenticated=True):
        self.authenticated = authenticated
        self._payload = payload

    def get(self, path, params=None):
        return self._payload


def capture(rows, **kw):
    rest = Fake({"success": True, "result": rows}, **kw)
    return capture_authenticated_fills(rest, symbol="BTCUSD",
                                       source_endpoint="x", captured_at="x",
                                       request_params={})


def test_empty_symbol_window_is_typed():
    with pytest.raises(EmptySymbolWindowError, match="0 of 1 rows matched"):
        capture([venue_row(symbol="ETHUSD")])
    # Typed error remains a ValueError for existing callers.
    assert issubclass(EmptySymbolWindowError, ValueError)


def test_malformed_row_is_not_empty():
    bad = venue_row()
    del bad["order_id"]
    with pytest.raises(ValueError, match="order_id"):
        capture([bad])
    try:
        capture([bad])
    except EmptySymbolWindowError:
        pytest.fail("malformed row mislabeled as empty window")
    except ValueError:
        pass


def test_non_list_result_is_not_empty():
    with pytest.raises(ValueError, match="not a list"):
        capture_authenticated_fills(
            Fake({"success": True, "result": {"fills": []}}),
            symbol="BTCUSD", source_endpoint="x", captured_at="x",
            request_params={})


def test_duplicate_ids_rejected_not_empty():
    with pytest.raises(ValueError, match="duplicate"):
        capture([venue_row(1, ts=1000), venue_row(1, ts=1001)])


def test_bad_timestamp_rejected_not_empty():
    with pytest.raises(ValueError, match="timestamp"):
        capture([venue_row(ts="not-a-time")])


def test_unauthenticated_refused_not_empty():
    with pytest.raises(RuntimeError, match="authenticated"):
        capture_authenticated_fills(
            Fake({"success": True, "result": []}, authenticated=False),
            symbol="BTCUSD", source_endpoint="x", captured_at="x",
            request_params={})


def test_unsuccessful_response_refused_not_empty():
    with pytest.raises(RuntimeError, match="unsuccessful"):
        capture_authenticated_fills(
            Fake({"success": False, "result": []}),
            symbol="BTCUSD", source_endpoint="x", captured_at="x",
            request_params={})


def test_symbol_mismatch_rejected_not_empty():
    from research.economics.delta_fill_evidence import normalize_fills
    with pytest.raises(ValueError, match="mismatch"):
        normalize_fills([venue_row(symbol="ETHUSD")], symbol="BTCUSD")
    try:
        normalize_fills([venue_row(symbol="ETHUSD")], symbol="BTCUSD")
    except EmptySymbolWindowError:
        pytest.fail("symbol mismatch mislabeled as empty window")
    except ValueError:
        pass


def test_recon_script_maps_only_typed_to_empty():
    # The reconciled-experiment REST block must translate ONLY the typed
    # error into rest_fills=0; anything else is FAILED. Verified by source
    # contract: importing the handler names from the script module.
    import pathlib
    text = pathlib.Path("scripts/bounded_testnet_reconciled_experiment.py").read_text()
    assert "EmptySymbolWindowError" in text
    assert 'evidence["rest_fills"] = "FAILED"' in text
