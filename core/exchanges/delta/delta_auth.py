"""
====================================================

Delta Exchange Signed REST Client

Private (authenticated) Delta v2 REST interface used by
the order executor and the account endpoints.

Delta signs every authenticated request with an HMAC-SHA256
signature. The signed (pre-hash) string is:

    method + timestamp + path_with_query + body

where every piece is plain string concatenation:

- method   : uppercase HTTP verb ("GET", "POST", "DELETE")
- timestamp: the same integer Unix seconds carried in the
             `timestamp` header, as a string
- path     : the request path INCLUDING any query string
             (e.g. "/v2/orders?product_id=1&state=open")
- body     : the exact request body string ("" for GET /
             DELETE). POST bodies must be serialized ONCE and
             both signed and sent byte-for-byte.

The `signature` header is the hex digest of that string keyed
by the API secret.

https://docs.delta.exchange (Authentication)

====================================================
"""

import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from core.exchanges.delta.write_authority import (
    KIND_LIVE_SAFETY,
    KIND_TESTNET_EXPERIMENT,
    consume_write_authority,
)

#: Write-authorized kinds accepted at the raw signed-REST boundary.
#: OFFLINE_TEST tokens are refused here on purpose: offline transport
#: tests must explicitly opt out with ``enforce_write_authority=False``
#: instead of riding an authorization that means nothing in production.
REST_WRITE_KINDS = frozenset({KIND_LIVE_SAFETY, KIND_TESTNET_EXPERIMENT})


def build_prehash(
    method,
    timestamp,
    path_with_query,
    body="",
):
    """
    Build the Delta signature pre-hash string.

    Delta concatenates method + timestamp + path(query) +
    body with NO separators.
    """
    return f"{method}{timestamp}{path_with_query}{body}"


def sign(
    api_secret,
    prehash,
):
    """
    HMAC-SHA256 of the prehash string keyed by the API
    secret, hex-encoded -- Delta's `signature` header.
    """
    return hmac.new(
        api_secret.encode("utf-8"),
        prehash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def query_string(params):
    """
    Deterministic query string for a params dict, matching the
    "path?k=v&k2=v2" form Delta signs. Returns "" when there
    are no params (no trailing "?").
    """
    if not params:
        return ""
    return "?" + urllib.parse.urlencode(params)


# -------------------------------------------------
# Venue authentication-failure taxonomy (diagnostics only).
#
# Maps a venue error code / HTTP status to a stable,
# credential-free classification. Pure function: no network,
# no secrets in, no secrets out. Used by evidence tooling to
# report WHY authentication failed without exposing anything
# sensitive.
# -------------------------------------------------

INVALID_API_KEY = "INVALID_API_KEY"
INVALID_SIGNATURE = "INVALID_SIGNATURE"
TIMESTAMP_ERROR = "TIMESTAMP_ERROR"
IP_NOT_WHITELISTED = "IP_NOT_WHITELISTED"
PERMISSION_DENIED = "PERMISSION_DENIED"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"

_KNOWN_AUTH_CODES = {
    "invalidapikey": INVALID_API_KEY,
    "invalid_api_key": INVALID_API_KEY,
    "signature mismatch": INVALID_SIGNATURE,
    "signature_mismatch": INVALID_SIGNATURE,
    "invalidsignature": INVALID_SIGNATURE,
    "signatureexpired": TIMESTAMP_ERROR,
    "signature_expired": TIMESTAMP_ERROR,
    "timestamp_expired": TIMESTAMP_ERROR,
    "ip_not_whitelisted_for_api_key": IP_NOT_WHITELISTED,
    "ip_not_whitelisted": IP_NOT_WHITELISTED,
    "unauthorizedapiaccess": PERMISSION_DENIED,
    "unauthorized_api_access": PERMISSION_DENIED,
    "forbidden": PERMISSION_DENIED,
}


def classify_auth_error(code, http_status=None):
    """Classify a venue authentication failure.

    `code` is the venue error code string (or anything
    else); `http_status` is the optional HTTP status.
    Returns one of the INVALID_API_KEY / INVALID_SIGNATURE /
    TIMESTAMP_ERROR / IP_NOT_WHITELISTED / PERMISSION_DENIED /
    AUTHENTICATION_FAILED constants. Never raises; never
    includes input values in a way that could leak secrets
    (codes are venue constants, echoed only by category).
    """
    try:
        normalized = str(code or "").strip().lower()
    except Exception:  # noqa: BLE001 (fail closed to generic)
        return AUTHENTICATION_FAILED
    if normalized in _KNOWN_AUTH_CODES:
        return _KNOWN_AUTH_CODES[normalized]
    if http_status == 401:
        return AUTHENTICATION_FAILED
    if http_status == 403:
        return PERMISSION_DENIED
    return AUTHENTICATION_FAILED


class DeltaSignedREST:
    """
    Signed Delta v2 REST client.

    Public endpoints work without credentials (get() ignores
    auth when no api key/secret is set); private endpoints
    (wallet/positions/orders) require DeltaExchange to guard
    them with _require_auth before calling.
    """

    BASE_URL = "https://api.delta.exchange"

    def __init__(
        self,
        api_key="",
        api_secret="",
        base_url=None,
        enforce_write_authority=True,
    ):

        self.api_key = api_key

        self.api_secret = api_secret

        self.base_url = base_url or self.BASE_URL

        # Phase193B: state-changing verbs are authorization-gated at this
        # boundary by default.  Receive-only callers are unaffected; offline
        # transport tests opt out explicitly (defs are pinned by regression
        # tests so the opt-out cannot silently appear in production paths).
        self.enforce_write_authority = bool(enforce_write_authority)

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=20,
        )

    # -------------------------------------------------

    @property
    def authenticated(self):

        return bool(
            self.api_key and self.api_secret
        )

    @property
    def provenance_identity(self):
        """Return the non-secret upstream origin bound to captured evidence."""
        parsed = urllib.parse.urlsplit(self.base_url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError("Delta REST base_url must include a scheme and hostname")
        hostname = parsed.hostname.lower()
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        authority = hostname
        if parsed.port is not None:
            authority = f"{authority}:{parsed.port}"
        return {
            "venue": "delta",
            "api_version": "v2",
            "origin": f"{parsed.scheme.lower()}://{authority}",
            "base_path": parsed.path.rstrip("/"),
        }

    # -------------------------------------------------

    def _validate_request_target(self, path):
        """Refuse absolute or authority-relative targets before signing credentials."""
        if (not isinstance(path, str)
                or any(ord(char) < 32 or ord(char) == 127 for char in path)):
            raise ValueError("Delta REST request path must be an origin-relative URL path")
        parsed = urllib.parse.urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise ValueError("Delta REST request path must not override the configured origin")
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise ValueError("Delta REST request path must be an origin-relative URL path")

        base = urllib.parse.urlsplit(self.base_url)
        if (base.scheme.lower() not in {"https", "http"} or not base.hostname
                or base.username is not None or base.password is not None
                or base.query or base.fragment):
            raise ValueError("Delta REST base_url must be a clean HTTP(S) origin")
        if self.authenticated and base.scheme.lower() != "https":
            raise ValueError("authenticated Delta REST requests require HTTPS")

    # -------------------------------------------------

    def _headers(
        self,
        method,
        path_with_query,
        body,
    ):

        headers = {
            "Content-Type": "application/json",
            # Delta mandates a User-Agent header; requests without
            # one risk CDN 4XX rejection before reaching the API.
            "User-Agent": "quantengine-delta-client",
        }

        if not self.authenticated:
            return headers

        timestamp = str(
            int(time.time())
        )

        prehash = build_prehash(
            method,
            timestamp,
            path_with_query,
            body,
        )

        headers["api-key"] = self.api_key

        headers["timestamp"] = timestamp

        headers["signature"] = sign(
            self.api_secret,
            prehash,
        )

        return headers

    # -------------------------------------------------

    def get(
        self,
        path,
        params=None,
    ):

        self._validate_request_target(path)
        path_with_query = (
            path + query_string(params)
        )

        last_exc = None
        for attempt in range(3):
            try:
                response = self.client.get(
                    path_with_query,
                    headers=self._headers(
                        "GET",
                        path_with_query,
                        "",
                    ),
                )
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                time.sleep(0.5 * (attempt + 1))
        if last_exc:
            raise last_exc

    def get_with_policy(
        self,
        path,
        params=None,
        *,
        timeout_seconds=20,
        retry_budget=2,
    ):
        """Bounded read-only GET with per-call timeout/retry controls.

        Returns (JSON payload, retry_count, HTTP status). Non-retryable 4xx
        responses fail immediately. 429 honors Retry-After; transient network
        and 5xx failures use capped exponential backoff without jitter.
        """
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not 1 <= timeout_seconds <= 60):
            raise ValueError("timeout_seconds must be between 1 and 60")
        if (isinstance(retry_budget, bool) or not isinstance(retry_budget, int)
                or not 0 <= retry_budget <= 5):
            raise ValueError("retry_budget must be between 0 and 5")
        self._validate_request_target(path)
        path_with_query = path + query_string(params)

        def retry_delay(response, attempt):
            fallback = min(0.5 * (2 ** attempt), 30.0)
            raw = response.headers.get("Retry-After") if response is not None else None
            if raw is None:
                return fallback
            try:
                return min(max(float(raw), 0.0), 30.0)
            except (TypeError, ValueError):
                try:
                    retry_at = parsedate_to_datetime(raw)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    return min(max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0), 30.0)
                except (TypeError, ValueError, OverflowError):
                    return fallback

        for attempt in range(retry_budget + 1):
            response = None
            try:
                response = self.client.get(
                    path_with_query,
                    headers=self._headers("GET", path_with_query, ""),
                    timeout=float(timeout_seconds),
                    follow_redirects=False,
                )
                status = response.status_code
                if (status == 429 or status >= 500) and attempt < retry_budget:
                    time.sleep(retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response.json(), attempt, status
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                if attempt < retry_budget:
                    time.sleep(min(0.5 * (2 ** attempt), 30.0))
                    continue
                exc.retry_count = attempt
                raise
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (429,) or (status is not None and status >= 500):
                    if attempt < retry_budget:
                        time.sleep(retry_delay(exc.response, attempt))
                        continue
                exc.retry_count = attempt
                raise

        raise RuntimeError("bounded GET retry loop exited unexpectedly")

    # -------------------------------------------------

    def post(
        self,
        path,
        payload=None,
        authority=None,
    ):

        self._validate_request_target(path)
        if self.enforce_write_authority:
            consume_write_authority(
                authority, base_url=self.base_url, endpoint=path,
                payload=payload, kinds=REST_WRITE_KINDS, method="POST",
            )

        # Serialize ONCE: the exact string sent on the wire is
        # the exact string used in the signature.
        body = (
            ""
            if payload is None
            else json.dumps(
                payload,
                separators=(",", ":"),
            )
        )

        response = self.client.post(
            path,
            content=body.encode("utf-8"),
            headers=self._headers(
                "POST",
                path,
                body,
            ),
        )

        response.raise_for_status()

        return response.json()

    # -------------------------------------------------

    def delete(
        self,
        path,
        payload=None,
        authority=None,
    ):

        if self.enforce_write_authority:
            consume_write_authority(
                authority, base_url=self.base_url, endpoint=path,
                payload=payload, kinds=REST_WRITE_KINDS, method="DELETE",
            )

        # Serialize ONCE, like post(): the exact string sent on the
        # wire is the exact string used in the signature. A DELETE
        # without payload signs and sends "" (legacy behavior,
        # byte-identical).
        body = (
            ""
            if payload is None
            else json.dumps(
                payload,
                separators=(",", ":"),
            )
        )

        # httpx 0.28 removed the `content` kwarg from the delete()
        # shortcut; request() supports it across pinned (0.27.2) and
        # installed (0.28.1) versions. Same wire bytes + signature.
        # Test fakes expose only delete(): prefer request() when the
        # underlying client offers it, else use the legacy shortcut.
        headers = self._headers(
            "DELETE",
            path,
            body,
        )
        if hasattr(self.client, "request"):
            response = self.client.request(
                "DELETE",
                path,
                content=body.encode("utf-8"),
                headers=headers,
            )
        else:
            response = self.client.delete(
                path,
                content=body.encode("utf-8"),
                headers=headers,
            )

        response.raise_for_status()

        return response.json()