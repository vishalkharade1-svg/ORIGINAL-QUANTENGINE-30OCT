"""Phase 91: shared Delta REST environment separation + snapshot provenance.

- DeltaREST() default still targets the legacy Global endpoint (no silent
  migration of existing callers).
- An explicit base_url is honored (Testnet selectable without code edits).
- Snapshot acquire() validates the envelope and pins provenance fields.
  All network access is mocked; nothing here touches a venue.
"""
import importlib.util
from pathlib import Path

from core.exchanges.delta.delta_rest import DeltaREST

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acquire_testnet_product_snapshot.py"
_spec = importlib.util.spec_from_file_location("testnet_snapshot", SCRIPT)
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)


class FakeClient:
    instances = []

    def __init__(self, base_url=None, timeout=None):
        self.base_url = base_url
        self.timeout = timeout
        FakeClient.instances.append(self)


def test_default_base_url_unchanged(monkeypatch):
    import httpx
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = DeltaREST()
    assert client.base_url == "https://api.delta.exchange"
    assert FakeClient.instances[-1].base_url == "https://api.delta.exchange"


def test_explicit_testnet_base_url_honored(monkeypatch):
    import httpx
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = DeltaREST(base_url="https://cdn-ind.testnet.deltaex.org/")
    assert client.base_url == "https://cdn-ind.testnet.deltaex.org"
    assert FakeClient.instances[-1].base_url == "https://cdn-ind.testnet.deltaex.org"


def _resp(entries=None, success=True):
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": success, "result": entries}
    return R()


def test_acquire_rejects_unsuccessful_envelope(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp([], success=False))
    try:
        snap.acquire(base_url="https://x", symbol="BTCUSD", observed_label="t")
    except RuntimeError:
        return
    raise AssertionError("unsuccessful envelope must raise")


def test_acquire_pins_provenance_and_single_match(monkeypatch):
    import httpx
    rows = [{"symbol": "ETHUSD"}, {"symbol": "BTCUSD", "tick_size": "0.1"}]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp(rows))
    out = snap.acquire(base_url="https://cdn-ind.testnet.deltaex.org",
                       symbol="BTCUSD", observed_label="unit")
    assert out["endpoint"] == "https://cdn-ind.testnet.deltaex.org/v2/products"
    assert out["auth"] == "none"
    assert out["catalog_population"] == 2
    assert out["product"]["tick_size"] == "0.1"
    assert out["is_production_ready"] is False
    assert len(out["catalog_sha256"]) == 64


def test_acquire_rejects_missing_and_ambiguous_symbol(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp([{"symbol": "ETHUSD"}]))
    for fn in (lambda: snap.acquire(base_url="https://x", symbol="BTCUSD", observed_label="t"),):
        try:
            fn()
        except RuntimeError:
            pass
        else:
            raise AssertionError("missing symbol must raise")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _resp([{"symbol": "BTCUSD"}, {"symbol": "BTCUSD"}]))
    try:
        snap.acquire(base_url="https://x", symbol="BTCUSD", observed_label="t")
    except RuntimeError:
        return
    raise AssertionError("ambiguous symbol must raise")


def test_history_and_products_accept_explicit_transport(monkeypatch):
    """Injected transports select the environment; defaults are unchanged."""
    import httpx
    from core.exchanges.delta.delta_history import DeltaHistory
    from core.exchanges.delta.delta_products import DeltaProducts
    FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "Client", FakeClient)
    marker = object()
    assert DeltaHistory(rest=marker).rest is marker
    assert DeltaProducts(rest=marker).rest is marker
    assert isinstance(DeltaHistory().rest, DeltaREST)
    assert isinstance(DeltaProducts().rest, DeltaREST)
    assert DeltaHistory().rest.base_url == "https://api.delta.exchange"


def test_historical_loader_base_url_selection():
    """HistoricalLoader defaults to Global; explicit host is honored."""
    from data.historical_loader import BASE_URL, HistoricalLoader

    default = HistoricalLoader()
    try:
        assert default.base_url == BASE_URL
        assert default.base_url == "https://api.delta.exchange"
        custom = HistoricalLoader(
            base_url="https://cdn-ind.testnet.deltaex.org/")
        try:
            assert custom.base_url == "https://cdn-ind.testnet.deltaex.org"
        finally:
            custom.close()
    finally:
        default.close()


def test_historical_loader_fetch_uses_configured_host():
    """_fetch hits the configured host path (mocked transport)."""
    from data.historical_loader import HistoricalLoader

    seen = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "result": []}

    class FakeBoundClient:
        def get(self, url, params=None):
            seen["url"] = url
            seen["params"] = dict(params or {})
            return FakeResp()

        def close(self):
            pass

    loader = HistoricalLoader(
        base_url="https://cdn-ind.testnet.deltaex.org")
    loader.client = FakeBoundClient()
    try:
        out = loader._fetch("BTCUSD", "1m", 1, 2)
    finally:
        loader.close()
    assert out == {"success": True, "result": []}
    assert seen["url"] == ("https://cdn-ind.testnet.deltaex.org"
                           "/v2/history/candles")
    assert seen["params"]["symbol"] == "BTCUSD"
