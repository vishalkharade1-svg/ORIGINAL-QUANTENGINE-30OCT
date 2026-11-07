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

    # -------------------------------------------------

    def post(
        self,
        path,
        payload=None,
        authority=None,
    ):

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