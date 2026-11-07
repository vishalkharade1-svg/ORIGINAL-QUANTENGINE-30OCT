"""Phase 93: control-API error responses must never carry credentials."""
from core.monitoring.api_server import _json_safe, _safe_detail


def test_safe_detail_redacts_configured_secrets(monkeypatch):
    monkeypatch.setenv("DELTA_API_KEY", "AK-SECRET-MARKER-123")
    monkeypatch.setenv("DELTA_API_SECRET", "AS-SECRET-MARKER-456")
    monkeypatch.setenv("CONTROL_API_TOKEN", "TOK-SECRET-MARKER-789")
    detail = _safe_detail(RuntimeError(
        "boom AK-SECRET-MARKER-123 / AS-SECRET-MARKER-456 / TOK-SECRET-MARKER-789"))
    assert "AK-SECRET-MARKER-123" not in detail
    assert "AS-SECRET-MARKER-456" not in detail
    assert "TOK-SECRET-MARKER-789" not in detail
    assert detail.count("[REDACTED]") == 3
    assert detail.startswith("boom")


def test_safe_detail_truncates_and_never_raises(monkeypatch):
    monkeypatch.delenv("DELTA_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_API_SECRET", raising=False)
    monkeypatch.delenv("CONTROL_API_TOKEN", raising=False)
    assert len(_safe_detail(ValueError("x" * 1000))) == 300

    class BadStr(Exception):
        def __str__(self):
            raise RuntimeError("no str for you")

    assert _safe_detail(BadStr()) == "unavailable"


def test_json_safe_exception_branch_redacts(monkeypatch):
    monkeypatch.setenv("DELTA_API_SECRET", "AS-SECRET-MARKER-456")
    # Standard exceptions serialize via vars() (normally {}); whatever
    # path is taken, a configured secret must never survive it.
    out = _json_safe(RuntimeError("failed with AS-SECRET-MARKER-456 inside"))
    assert "AS-SECRET-MARKER-456" not in str(out)
