"""Phase155: urlopen scheme-allowlist hardening (bandit B310).

Three `urllib.request.urlopen` call sites were flagged MEDIUM (B310:
"Audit url open for permitted schemes"). Each now refuses any scheme
other than http/https before opening a request. These tests exercise the
guards offline (no sockets) and pin the source contract for the one site
whose URL is built with a literal `http://` prefix.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestClientSchemeGuard(unittest.TestCase):
    def test_control_client_refuses_file_scheme(self):
        from core.client.http_client import ApiClient
        client = ApiClient(host="127.0.0.1", port=1, token="t")
        client.base_url = lambda: "file:///etc"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            client._open("GET", "/health")

    def test_control_client_refuses_ftp_scheme(self):
        from core.client.http_client import ApiClient
        client = ApiClient(host="127.0.0.1", port=1, token="t")
        client.base_url = lambda: "ftp://example.com"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            client._open("GET", "/health")


class TestEvidenceGateSchemeGuard(unittest.TestCase):
    def test_http_refuses_file_scheme(self):
        mod = _load("phase155_eeg", "scripts/evaluate_evidence_gates.py")
        with self.assertRaises(ValueError):
            mod._http("file:///etc", "/passwd")

    def test_http_allows_http_scheme(self):
        # Guard passes for http; connection then fails, and the helper
        # degrades to (None, b"") rather than raising.
        mod = _load("phase155_eeg2", "scripts/evaluate_evidence_gates.py")
        status, body = mod._http("http://127.0.0.1:1", "/nope", timeout=0.5)
        self.assertIsNone(status)
        self.assertEqual(body, b"")


class TestGatewaySchemeGuard(unittest.TestCase):
    def test_gateway_source_pins_scheme_guard(self):
        text = (ROOT / "core" / "remote" / "gateway.py").read_text(encoding="utf-8")
        self.assertIn("_urlparse.urlparse(url).scheme", text)
        self.assertIn('"unsupported URL scheme"', text)
        # The forward URL is built with a literal http:// prefix, so the
        # guard is defense-in-depth rather than a reachable path today.
        self.assertIn('url = "http://%s:%d%s"', text)


if __name__ == "__main__":
    unittest.main()
