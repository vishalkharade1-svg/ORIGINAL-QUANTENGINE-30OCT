import importlib.util
from pathlib import Path
import os
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_phase85_delta_testnet_capture.py"
spec = importlib.util.spec_from_file_location("phase85_capture", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_environment_endpoint_validation_rejects_production_mix():
    with pytest.raises(ValueError):
        mod.validate_endpoints("india_testnet", rest_base_url="https://api.india.delta.exchange",
                               private_ws_url="wss://socket.india.delta.exchange")


def test_redaction_never_returns_environment_secrets(monkeypatch):
    monkeypatch.setenv("DELTA_INDIA_TESTNET_API_KEY", "key-secret-example")
    monkeypatch.setenv("DELTA_INDIA_TESTNET_API_SECRET", "secret-secret-example")
    msg = mod.redact_error(RuntimeError("key-secret-example secret-secret-example"))
    assert "key-secret-example" not in msg
    assert "secret-secret-example" not in msg
    assert "[REDACTED]" in msg


def test_generic_credentials_are_not_reinterpreted_as_india_testnet(monkeypatch, tmp_path):
    monkeypatch.setenv("DELTA_API_KEY", "production-key-placeholder")
    monkeypatch.setenv("DELTA_API_SECRET", "production-secret-placeholder")
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_SECRET", raising=False)
    monkeypatch.setattr(mod, "dns_probe", lambda hosts: {h: {"status": "RESOLVED", "address_count": "1"} for h in hosts})
    import research.economics.delta_live_capture as live_mod
    async def _fail(**kwargs):
        raise RuntimeError("simulated public-channel failure")
    monkeypatch.setattr(live_mod, "capture_live", _fail)
    args = type("Args", (), {
        "environment":"india_testnet", "rest_url":None, "private_ws_url":None,
        "public_ws_url":None, "symbol":"BTCUSD", "capture_id":"test-capture",
        "duration":1.0, "min_observations":2, "output_dir":str(tmp_path), "page_size":100,
    })()
    import asyncio
    report = asyncio.run(mod.run(args))
    assert report["authenticated_rest_fills"] == "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
    assert report["private_ws_fills"] == "BLOCKED_CREDENTIALS_NOT_CONFIGURED"


def test_missing_credentials_blocks_before_authenticated_calls(monkeypatch, tmp_path):
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_SECRET", raising=False)
    monkeypatch.setattr(mod, "dns_probe", lambda hosts: {h: {"status": "RESOLVED", "address_count": "1"} for h in hosts})
    # Public L2 needs no credentials: force a deterministic failure so the
    # test never touches the real network.
    import research.economics.delta_live_capture as live_mod
    async def _fail(**kwargs):
        raise RuntimeError("simulated public-channel failure")
    monkeypatch.setattr(live_mod, "capture_live", _fail)
    args = type("Args", (), {
        "environment":"india_testnet", "rest_url":None, "private_ws_url":None,
        "public_ws_url":None, "symbol":"BTCUSD", "capture_id":"test-capture",
        "duration":1.0, "min_observations":2, "output_dir":str(tmp_path), "page_size":100,
    })()
    import asyncio
    report = asyncio.run(mod.run(args))
    # Authenticated legs must stay blocked without credentials; public L2 is
    # attempted independently (here forced to FAILED deterministically).
    assert report["authenticated_rest_fills"] == "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
    assert report["private_ws_fills"] == "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
    assert report["real_public_l2"] == "FAILED"
    assert report["credentials_persisted"] is False
    assert report["order_placement"] == "DISABLED"


def test_missing_credentials_still_attempts_public_l2(monkeypatch, tmp_path):
    """Public ob_updates capture must not be gated behind API credentials."""
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_SECRET", raising=False)
    monkeypatch.setattr(mod, "dns_probe", lambda hosts: {h: {"status": "RESOLVED", "address_count": "1"} for h in hosts})
    import research.economics.delta_live_capture as live_mod
    seen = {}
    async def _ok(*, endpoint, symbol, duration_seconds, identity, min_observations=2, **kw):
        seen["called"] = True
        raise RuntimeError("simulated empty feed")
    monkeypatch.setattr(live_mod, "capture_live", _ok)
    args = type("Args", (), {
        "environment":"india_testnet", "rest_url":None, "private_ws_url":None,
        "public_ws_url":None, "symbol":"BTCUSD", "capture_id":"test-capture",
        "duration":1.0, "min_observations":2, "output_dir":str(tmp_path), "page_size":100,
    })()
    import asyncio
    report = asyncio.run(mod.run(args))
    assert seen.get("called") is True
    assert report["authenticated_rest_fills"] == "BLOCKED_CREDENTIALS_NOT_CONFIGURED"


def test_empty_authenticated_fills_reported_empty_not_success(monkeypatch, tmp_path):
    """An authenticated-but-empty /v2/fills must be EMPTY, never CAPTURED."""
    monkeypatch.setenv("DELTA_INDIA_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("DELTA_INDIA_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setattr(mod, "dns_probe", lambda hosts: {h: {"status": "RESOLVED", "address_count": "1"} for h in hosts})
    import research.economics.delta_fill_evidence as fill_mod
    import research.economics.delta_live_capture as live_mod
    import research.economics.delta_private_fill_capture as priv_mod

    def _empty(rest, **kwargs):
        from research.economics.delta_fill_evidence import EmptySymbolWindowError
        raise EmptySymbolWindowError("fill evidence must be non-empty (0 of 1 rows matched symbol BTCUSD)")

    async def _fail(**kwargs):
        raise RuntimeError("simulated public-channel failure")

    async def _no_private(**kwargs):
        raise RuntimeError("simulated private-channel failure")

    monkeypatch.setattr(fill_mod, "capture_authenticated_fills", _empty)
    monkeypatch.setattr(live_mod, "capture_live", _fail)
    monkeypatch.setattr(priv_mod, "capture_live", _no_private)
    args = type("Args", (), {
        "environment": "india_testnet", "rest_url": None, "private_ws_url": None,
        "public_ws_url": None, "symbol": "BTCUSD", "capture_id": "test-capture",
        "duration": 1.0, "min_observations": 2, "output_dir": str(tmp_path), "page_size": 100,
    })()
    import asyncio
    report = asyncio.run(mod.run(args))
    assert report["authenticated_rest_fills"] == "EMPTY_RESPONSE"
    assert report.get("rest_fill_count") == 0
    assert not (tmp_path / "rest_fills.json").exists()


def test_capture_identity_testnet_uses_sandbox(monkeypatch):
    """Testnet captures must stamp SANDBOX: CaptureIdentity rejects
    anything but PRODUCTION/SANDBOX (regression pin for the
    reconciled-experiment L2 failure that passed INDIA_TESTNET)."""
    from research.economics.market_friction_capture import CaptureIdentity
    import pytest
    good = CaptureIdentity(
        venue="delta", environment="SANDBOX", symbol="BTCUSD",
        source_endpoint="wss://socket-ind-pub.testnet.deltaex.org",
        transport="LIVE_CAPTURE", capture_id="pin")
    good.validate()
    bad = CaptureIdentity(
        venue="delta", environment="INDIA_TESTNET", symbol="BTCUSD",
        source_endpoint="wss://socket-ind-pub.testnet.deltaex.org",
        transport="LIVE_CAPTURE", capture_id="pin")
    with pytest.raises(ValueError, match="PRODUCTION or SANDBOX"):
        bad.validate()


def test_dns_probe_reports_errors_without_secrets(monkeypatch):
    monkeypatch.setattr(mod.socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(OSError("DNS blocked")))
    result = mod.dns_probe(["example.invalid"])
    assert result["example.invalid"]["status"] == "BLOCKED"
    assert "DNS blocked" in result["example.invalid"]["error"]


def test_signed_rest_canonical_query_and_user_agent(monkeypatch):
    """Signature must cover the exact query string sent, with User-Agent set.

    Docs: prehash = method + timestamp + requestPath + query params + body;
    User-Agent header is mandatory to avoid CDN 4XX.
    """
    import hashlib
    import hmac as hmac_mod
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "result": []}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    client = mod.SignedDeltaREST("https://cdn-ind.testnet.deltaex.org", "k", "s")
    # Unsorted input: wire URL must carry the sorted canonical query.
    client.get("/v2/fills", params={"symbol": "BTCUSD", "page_size": 100})
    assert captured["url"].endswith("/v2/fills?page_size=100&symbol=BTCUSD")
    ts = captured["headers"]["timestamp"]
    expected = hmac_mod.new(b"s", ("GET" + ts + "/v2/fills?page_size=100&symbol=BTCUSD").encode(),
                            hashlib.sha256).hexdigest()
    assert captured["headers"]["signature"] == expected
    assert captured["headers"]["User-Agent"] == "quantengine-phase85-capture"
    assert captured["headers"]["api-key"] == "k"
    assert "s" not in list(captured["headers"].values())
