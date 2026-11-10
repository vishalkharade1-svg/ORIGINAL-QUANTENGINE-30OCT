"""
Process-minted write authority for Delta exchange writes.

Phase193B closes the Phase 189+ audit finding that the low-level write
boundary (``DeltaExchange.place_order``/``cancel_order`` and the raw
``DeltaSignedREST.post``/``delete``) enforced only *authentication*: any
caller that assembled the right client could submit an order without the
mandatory authorization stages (LiveSafetyGate / TestnetAuthorizationGate).

Design (matches the existing gate mint discipline):

  * Every armed write carries a ``WriteAuthorityToken`` stamped with THIS
    process's mint secret.  The token cannot be hand-constructed outside
    this module's issue functions (``__init__`` is private; dataclass
    freezes it; the mint is never logged or serialized).
  * Issue functions verify the upstream authorization themselves:
      - ``token_for_live_safety`` re-plays ``LiveSafetyGate.require_decision``
        so a stale/forged SafetyDecision can never arm a transport.
      - ``token_for_testnet_experiment`` requires a gate-minted
        ``AuthorizationDecision`` that ``is_armed()``.
      - ``offline_test_token`` exists ONLY for unit tests driving fake
        transports; it is process-minted like everything else and must
        never be reachable from production entrypoints.
  * ``require_write_authority`` binds the token to the exact venue URL,
    endpoint, HTTP method, write kind, and canonical JSON payload. The
    signed REST boundary consumes each production token once, so a token
    cannot be replayed or moved between POST placement and DELETE cancel.

Nothing here ever strings-formats secret material; reasons name only the
missing KINDS or binding mismatches.

Hard rules:  pure stdlib; no network; no file I/O; no global mutable
state beyond the process mint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import secrets
import threading

_MINT = secrets.token_hex(32)
_CONSUMED_NONCES = set()
_CONSUMED_LOCK = threading.Lock()

KIND_OFFLINE_TEST = "OFFLINE_TEST"
KIND_LIVE_SAFETY = "LIVE_SAFETY"
KIND_TESTNET_EXPERIMENT = "TESTNET_EXPERIMENT"

#: All authorized kinds.  Independent verification is by kind, so one
#: authorization family can never silently ride over another.
ALL_KINDS = frozenset({KIND_OFFLINE_TEST, KIND_LIVE_SAFETY,
                       KIND_TESTNET_EXPERIMENT})

#: Base-URL normalization for offline fake transports (no ``base_url``).
OFFLINE_FALLBACK_BASE_URL = "offline-fake-transport"


class TransportWriteAuthorityError(RuntimeError):
    """An exchange write was attempted without a valid armed token."""


@dataclass(frozen=True)
class WriteAuthorityToken:
    """Armed transport-write token (see module docstring)."""
    mint: str = field(repr=False)
    kind: str
    base_url: str
    endpoint: str
    payload_sha256: str = ""
    method: str = "POST"
    nonce: str = field(default_factory=lambda: secrets.token_hex(16), repr=False)

    def __post_init__(self):
        if self.mint != _MINT:
            raise TransportWriteAuthorityError(
                "write-authority token mint does not match this process "
                "(forged or stale token)")
        if self.kind not in ALL_KINDS:
            raise TransportWriteAuthorityError(
                "unknown write-authority kind {!r}".format(self.kind))


def _payload_digest(payload) -> str:
    """Hash the semantic JSON payload, independent of dictionary key order."""
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TransportWriteAuthorityError(
            "write authority requires a finite JSON-compatible payload") from exc
    return hashlib.sha256(encoded).hexdigest()


def _infer_write_method(payload) -> str:
    """Infer the only supported orders endpoint operation from its payload shape.

    Delta uses POST /v2/orders for placement and DELETE /v2/orders for
    cancellation. A cancellation payload must have exactly ``id`` and
    ``product_id``; malformed order payloads default to POST and are then
    validated against the placement schema below.
    """
    if isinstance(payload, dict) and set(payload) == {"id", "product_id"}:
        return "DELETE"
    return "POST"


def _issue(kind: str, base_url: str, endpoint: str,
           payload=None, method: str = "POST") -> WriteAuthorityToken:
    method = str(method).upper()
    if kind != KIND_OFFLINE_TEST and method not in {"POST", "DELETE"}:
        raise TransportWriteAuthorityError("write authority requires POST or DELETE method")
    digest = "" if kind == KIND_OFFLINE_TEST else _payload_digest(payload)
    return WriteAuthorityToken(mint=_MINT, kind=kind,
                               base_url=base_url, endpoint=endpoint,
                               payload_sha256=digest,
                               method="ANY" if kind == KIND_OFFLINE_TEST else method)


def offline_test_token(base_url: str = OFFLINE_FALLBACK_BASE_URL,
                       endpoint: str = "/v2/orders") -> WriteAuthorityToken:
    """TEST-ONLY authority for fake transports.

    Production entrypoints must never call this: real writes must be
    armed by the safety/authorization gates instead.  The kind marks the
    token so a mixed gate can assert it is absent.
    """
    return _issue(KIND_OFFLINE_TEST, base_url, endpoint)


def _bind_base_url(base_url) -> str:
    """Normalize the armed-base-URL string for binding checks."""
    return str(base_url) if base_url is not None and str(base_url) != "" else OFFLINE_FALLBACK_BASE_URL


def token_for_live_safety(decision, base_url, *, payload,
                          endpoint: str = "/v2/orders", method: str | None = None
                          ) -> WriteAuthorityToken:
    """Arm a transport write from a minted ``LiveSafetyGate`` decision.

    The decision is re-verified through ``LiveSafetyGate.require_decision``
    so hand-built or stale tokens fail closed before the issue.
    """
    from core.execution.live_safety_gate import LiveSafetyGate

    verified = LiveSafetyGate.require_decision(
        decision, component="write_authority.token_for_live_safety")
    if (getattr(verified, "_authority", "") == "OFFLINE_TEST"
            and _bind_base_url(base_url) != OFFLINE_FALLBACK_BASE_URL):
        raise TransportWriteAuthorityError(
            "OFFLINE_TEST safety capability cannot authorize a configured exchange endpoint")
    resolved_method = str(method or _infer_write_method(payload)).upper()
    return _issue(KIND_LIVE_SAFETY, _bind_base_url(base_url), endpoint, payload, resolved_method)


def token_for_testnet_experiment(decision, base_url, *, payload,
                                 endpoint: str = "/v2/orders", method: str | None = None
                                 ) -> WriteAuthorityToken:
    """Arm a transport write from an armed testnet authorization decision.

    Requires an ``AuthorizationDecision`` minted by
    ``TestnetAuthorizationGate.evaluate_preflight`` (``is_armed()``).
    """
    is_armed = getattr(decision, "is_armed", None)
    if not callable(is_armed) or not decision.is_armed():
        raise TransportWriteAuthorityError(
            "testnet experiment write requires an armed "
            "TestnetAuthorizationGate decision (PENDING_OPERATOR_APPROVAL "
            "or refused scope arms nothing)")
    if not isinstance(payload, dict):
        raise TransportWriteAuthorityError("testnet write payload must be a JSON object")
    resolved_method = str(method or _infer_write_method(payload)).upper()
    if resolved_method not in {"POST", "DELETE"}:
        raise TransportWriteAuthorityError("testnet write method must be POST or DELETE")
    try:
        if int(payload.get("product_id")) != int(decision.authorized_product_id):
            raise TransportWriteAuthorityError(
                "testnet payload product_id differs from the preflight-authorized product")
    except (TypeError, ValueError):
        raise TransportWriteAuthorityError(
            "testnet payload has no valid product_id matching preflight")

    if resolved_method == "POST":
        required = {"product_id", "size", "side"}
        missing = sorted(required.difference(payload))
        if missing:
            raise TransportWriteAuthorityError(
                "testnet order payload missing required fields: " + ", ".join(missing))
        if str(payload.get("side", "")).lower() not in {"buy", "sell"}:
            raise TransportWriteAuthorityError("testnet order payload side must be buy or sell")
        from decimal import Decimal, InvalidOperation
        try:
            size = Decimal(str(payload["size"]))
            authorized_size = Decimal(str(decision.authorized_order_size_contracts))
            if not size.is_finite() or size <= 0 or size != authorized_size:
                raise TransportWriteAuthorityError(
                    "testnet payload size differs from the preflight-authorized size")
        except (InvalidOperation, TypeError, ValueError):
            raise TransportWriteAuthorityError("testnet payload size is invalid")
        if decision.authorized_post_only and payload.get("post_only") is not True:
            raise TransportWriteAuthorityError(
                "testnet payload must preserve the preflight-required post_only flag")
        details = dict(getattr(decision, "authorized_order_details", ()) or ())
        for key in ("side", "limit_price", "post_only"):
            if key in details and str(payload.get(key)) != details[key]:
                raise TransportWriteAuthorityError(
                    "testnet payload field %s differs from the reserved order details" % key)
        client_order_id = getattr(decision, "authorized_client_order_id", "")
        if client_order_id and str(payload.get("client_order_id", "")) != client_order_id:
            raise TransportWriteAuthorityError(
                "testnet payload client_order_id differs from the atomic reservation")
    else:
        if set(payload) != {"id", "product_id"}:
            raise TransportWriteAuthorityError(
                "testnet cancellation payload must contain only id and product_id")
        try:
            if int(payload["id"]) <= 0:
                raise ValueError("non-positive order id")
        except (TypeError, ValueError):
            raise TransportWriteAuthorityError("testnet cancellation requires a positive order id")
    return _issue(KIND_TESTNET_EXPERIMENT, _bind_base_url(base_url), endpoint, payload, resolved_method)


def require_write_authority(token, *, base_url: str, endpoint: str,
                            kinds: frozenset = ALL_KINDS, payload=None, method: str | None = None
                            ) -> WriteAuthorityToken:
    """Fail closed: return the validated token or raise.

    Refuses: no token, forged/de-serialized tokens (mint mismatch),
    unbound base URL, unbound endpoint, and unauthorized kind for this
    boundary.

    The *endpoint* argument accepts exactly one path; a token scoped to
    ``/v2/orders`` cannot authorize ``/v2/positions``. When supplied,
    ``method`` must also match exactly (POST placement versus DELETE cancel).
    """
    if token is None:
        raise TransportWriteAuthorityError(
            "exchange write refused: no write authority provided "
            "(Delta adapter writes are authorization-gated at the "
            "transport boundary since Phase193B)")
    if not isinstance(token, WriteAuthorityToken):
        raise TransportWriteAuthorityError(
            "exchange write refused: token is not a minted "
            "WriteAuthorityToken")
    if token.mint != _MINT:
        raise TransportWriteAuthorityError(
            "exchange write refused: token was not minted by this "
            "process")
    if token.kind == KIND_OFFLINE_TEST and KIND_OFFLINE_TEST not in kinds:
        raise TransportWriteAuthorityError(
            "exchange write refused: OFFLINE_TEST authority is not "
            "valid for this boundary")
    if token.kind not in kinds:
        raise TransportWriteAuthorityError(
            "exchange write refused: token kind {!r} is not allowed "
            "for this boundary (requires one of {!r})".format(
                token.kind, sorted(kinds)))
    if token.base_url != _bind_base_url(base_url):
        raise TransportWriteAuthorityError(
            "exchange write refused: token is armed for endpoint host "
            "{!r}, not {!r}".format(token.base_url, base_url))
    if token.endpoint != endpoint:
        raise TransportWriteAuthorityError(
            "exchange write refused: token is armed for {!r}, not "
            "{!r}".format(token.endpoint, endpoint))
    if token.kind != KIND_OFFLINE_TEST and method is not None:
        expected_method = str(method).upper()
        if token.method != expected_method:
            raise TransportWriteAuthorityError(
                "exchange write refused: token is armed for HTTP method %s, not %s" %
                (token.method, expected_method))
    if token.kind != KIND_OFFLINE_TEST:
        if not token.payload_sha256:
            raise TransportWriteAuthorityError(
                "exchange write refused: authority is not bound to an exact payload")
        if _payload_digest(payload) != token.payload_sha256:
            raise TransportWriteAuthorityError(
                "exchange write refused: payload differs from the preflight-authorized payload")
    return token


def consume_write_authority(token, *, base_url: str, endpoint: str,
                            payload, kinds: frozenset, method: str | None = None) -> WriteAuthorityToken:
    """Validate and atomically consume a production write token exactly once."""
    validated = require_write_authority(
        token, base_url=base_url, endpoint=endpoint, kinds=kinds,
        payload=payload, method=method)
    if validated.kind == KIND_OFFLINE_TEST:
        return validated
    with _CONSUMED_LOCK:
        if validated.nonce in _CONSUMED_NONCES:
            raise TransportWriteAuthorityError(
                "exchange write refused: write authority token has already been consumed")
        _CONSUMED_NONCES.add(validated.nonce)
    return validated
