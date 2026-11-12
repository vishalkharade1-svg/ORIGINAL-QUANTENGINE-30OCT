"""Phase193B transport write-authority enforcement: exploding-mock tests.

Guarantees pinned here (any unexpected venue write FAILS the test):
  * A PENDING_OPERATOR_APPROVAL authorization arms NOTHING: the gate
    preflight refuses, ``token_for_testnet_experiment`` raises, and the
    transport performs ZERO writes (exploding client catch).
  * Token forging (foreign mint), wrong kinds, wrong base URLs, wrong
    endpoints, and missing tokens are all refused at the boundary.
  * OFFLINE_TEST authority is never valid at the signed-REST boundary.
  * An armed TESTNET_EXPERIMENT decision mints a token bound to
    (testnet base_url, /v2/orders) that authorizes the experiment's
    bounded writes, and nothing outside that binding.

Zero network I/O: the httpx client on every DeltaSignedREST instance is
replaced with an offline recording/exploding double.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import httpx  # noqa: E402  (module attr patched in script-level tests)
import bounded_testnet_order_experiment as exp  # noqa: E402
import bounded_testnet_reconciled_experiment as recon  # noqa: E402
import funding_settlement_hold as funding  # noqa: E402

from core.exchanges.delta.delta_auth import (
    REST_WRITE_KINDS,
    DeltaSignedREST,
)
from core.exchanges.delta.delta_exchange import DeltaExchange
from core.exchanges.delta.write_authority import (
    KIND_LIVE_SAFETY,
    KIND_OFFLINE_TEST,
    KIND_TESTNET_EXPERIMENT,
    TransportWriteAuthorityError,
    WriteAuthorityToken,
    offline_test_token,
    require_write_authority,
    token_for_testnet_experiment,
)
from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
)
from authorization_test_utils import configure_test_verification_key, sign_record_for_test

TESTNET_REST = "https://cdn-ind.testnet.deltaex.org"

# Offline venue fixtures shared by the script-flow tests. Values are chosen
# to satisfy the explicitly bounded $100 notional cap without contacting
# Delta or relying on operator credentials.
_PRODUCTS_ROW = {
    "id": 84,
    "symbol": "BTCUSD",
    "contract_type": "perpetual_futures",
    "state": "live",
    "trading_status": "operational",
    "tick_size": "0.1",
    "contract_size": "0.001",
}
_TOUCH_BOOK = {
    "result": {
        "buy": [{"price": "50000.5"}],
        "sell": [{"price": "50010.0"}],
    }
}
_ETH_TOUCH_BOOK = {
    "result": {
        "buy": [{"price": "3500.00"}],
        "sell": [{"price": "3500.05"}],
    }
}

PENDING_CONTENT = (
    "# TESTNET ORDER EXPERIMENT AUTHORIZATION\n"
    "## Status: PENDING_OPERATOR_APPROVAL\n"
    "- **Authorization ID**: P189-AUTH-TEMPLATE\n"
    "- **Authorizing Operator**: [OPERATOR_IDENTITY]\n"
    "- **Operator Signature**: [OPERATOR_SIGNATURE]\n"
)

# Unsigned-looking but structurally APPROVED canary: no placeholders,
# no PENDING status, operator + signature present.
def _signed_approved_content():
    now = time.time()
    signed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2))
    expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600))
    raw = (
        "# TESTNET ORDER EXPERIMENT AUTHORIZATION\n\n"
        "- **Authorization ID**: P193B-CANARY-001\n"
        "- **Authorizing Operator**: phase193b-canary-operator\n"
        f"- **Signed Timestamp UTC**: {signed_at}\n"
        f"- **Expiry Timestamp UTC**: {expires_at}\n"
        "- **Operator Signature**: QE-P193B-CANARY-SIGNATURE\n"
    )
    parser = TestnetAuthorizationGate(ledger_path=Path(tempfile.gettempdir()) / "qe-phase193b-fixture-ledger.jsonl")
    record = parser.parse_authorization_document(raw)
    configure_test_verification_key()
    signature = sign_record_for_test(record)
    return raw.replace("QE-P193B-CANARY-SIGNATURE", signature)


APPROVED_CONTENT = _signed_approved_content()


class _ExplodingTransport:
    """Counts venue writes and raises on ANY reached write.

    Any ``len(write_calls) > 0`` means the enforcement layer let a
    write through when entertainment expected zero - test fails.
    """

    def __init__(self):
        self.write_calls = []

    def get(self, url, headers=None):
        return _FakeResponse({})

    def post(self, url, content=None, headers=None):
        self.write_calls.append(
            ("post", url, (content or b"").decode("utf-8")))
        raise AssertionError("TRANSPORT_WRITE_REACHED " + url)

    def delete(self, url, content=None, headers=None):
        self.write_calls.append(
            ("delete", url, (content or b"").decode("utf-8")))
        raise AssertionError("TRANSPORT_WRITE_REACHED " + url)


class _RecordingTransport:
    """Accepts posts/deletes (fake transport); records every write."""

    def __init__(self):
        self.calls = []

    def get(self, url, headers=None):
        return _FakeResponse({})

    def post(self, url, content=None, headers=None):
        self.calls.append(
            ("post", url, (content or b"").decode("utf-8")))
        return _FakeResponse({"success": True})

    def delete(self, url, content=None, headers=None):
        self.calls.append(
            ("delete", url, (content or b"").decode("utf-8")))
        return _FakeResponse({"success": True})


class _FakeResponse:

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Harness:

    def __init__(self, content):
        self.tmp = tempfile.TemporaryDirectory()
        ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=ledger)
        self.record = self.gate.parse_authorization_document(content)

    def cleanup(self):
        self.tmp.cleanup()


def _reserve_order_for_test(gate, record, *, cl_ord_id="P193B-ORDER-01",
                            side="buy", limit_price="80000",
                            symbol="BTCUSD", product_id=84,
                            size=Decimal(1), post_only=True):
    """Mint a write capability only through a durable order reservation."""
    return gate.check_and_reserve_order(
        auth_record=record,
        rest_url=TESTNET_REST,
        symbol=symbol,
        product_id=product_id,
        order_size_contracts=size,
        cl_ord_id=cl_ord_id,
        order_details={
            "side": side,
            "limit_price": str(limit_price),
            "post_only": post_only,
        },
        post_only=post_only,
    )


class TestPendingAuthorizationArmsNothing(unittest.TestCase):

    def setUp(self):
        self.h = _Harness(PENDING_CONTENT)

    def tearDown(self):
        self.h.cleanup()

    def test_pending_record_refused(self):
        # The template carries placeholders, so the gate latches it in
        # the PENDING lifecycle state and considers it never valid.
        self.assertEqual(
            self.h.record.state.value, "PENDING_OPERATOR_APPROVAL")
        self.assertFalse(self.h.record.is_currently_valid())

    def test_preflight_refused_with_pending_reason(self):
        decision = self.h.gate.evaluate_preflight(
            auth_record=self.h.record,
            rest_url=TESTNET_REST,
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal(1),
            post_only=True,
        )
        self.assertFalse(decision.is_armed())
        self.assertTrue(
            any("PENDING_OPERATOR_APPROVAL" in r for r in decision.reasons))

    def test_pending_decision_cannot_mint_transport_token(self):
        decision = self.h.gate.evaluate_preflight(
            auth_record=self.h.record,
            rest_url=TESTNET_REST,
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal(1),
            post_only=True,
        )
        with self.assertRaises(TransportWriteAuthorityError):
            token_for_testnet_experiment(decision,
                                         base_url=TESTNET_REST, payload={"size": 1})

    def test_pending_chain_performs_zero_transport_writes(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self.h.gate.evaluate_preflight(
            auth_record=self.h.record,
            rest_url=TESTNET_REST,
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal(1),
            post_only=True,
        )
        with self.assertRaises(TransportWriteAuthorityError):
            token_for_testnet_experiment(decision,
                                         base_url=TESTNET_REST, payload={"size": 1})
        # no authority at all: the direct boundary attempts also refuse
        with self.assertRaises(TransportWriteAuthorityError):
            rest.post("/v2/orders", payload={"size": 1})
        with self.assertRaises(TransportWriteAuthorityError):
            rest.delete("/v2/orders", payload={"id": 1, "product_id": 84})
        self.assertEqual(transport.write_calls, [])


class _LegacyRestDouble:
    """Pre-Phase193B offline double: no enforce_write_authority attr,
    legacy post(url, payload=...) / delete(url, payload=...) surfaces."""

    def __init__(self):
        self.base_url = TESTNET_REST
        self.calls = []

    @property
    def authenticated(self):
        return True

    def get(self, url, params=None):
        return {"result": {}}

    def post(self, url, payload=None):
        self.calls.append(("post", url, payload))
        return {"success": True}

    def delete(self, url, payload=None):
        self.calls.append(("delete", url, payload))
        return {"success": True}


class TestAdapterPassesAuthorityToEnforcingRest(unittest.TestCase):

    def setUp(self):
        self.h = _Harness(APPROVED_CONTENT)
        self.transport = _RecordingTransport()
        self.rest = DeltaSignedREST(api_key="canary-key",
                                    api_secret="canary-secret",
                                    base_url=TESTNET_REST)
        self.rest.client = self.transport
        self.exchange = DeltaExchange(api_key="canary-key",
                                      api_secret="canary-secret",
                                      rest=self.rest)

    def tearDown(self):
        self.h.cleanup()

    def _armed_token(self):
        decision = _reserve_order_for_test(self.h.gate, self.h.record)
        return token_for_testnet_experiment(
            decision, base_url=TESTNET_REST,
            payload={
                "product_id": 84, "size": "1", "side": "buy",
                "limit_price": "80000", "post_only": True,
                "client_order_id": "P193B-ORDER-01",
            })

    def test_place_order_writes_once_through_enforced_rest(self):
        token = self._armed_token()
        self.exchange.place_order(
            {
                "product_id": 84, "size": "1", "side": "buy",
                "limit_price": "80000", "post_only": True,
                "client_order_id": "P193B-ORDER-01",
            },
            authority=token,
        )
        self.assertEqual([c[0] for c in self.transport.calls],
                         ["post"])

    def test_cancel_order_writes_once_through_enforced_rest(self):
        decision = _reserve_order_for_test(self.h.gate, self.h.record)
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST,
            payload={"id": 123, "product_id": 84}, method="DELETE")
        self.exchange.cancel_order(123, product_id=84, authority=token)
        self.assertEqual([c[0] for c in self.transport.calls],
                         ["delete"])
        self.assertEqual(self.transport.calls[0][1], "/v2/orders")

    def test_offline_token_stops_at_the_enforcing_rest_boundary(self):
        # Adapter accepts every minted kind, but an OFFLINE_TEST token
        # is refused by the enforced production REST boundary beneath
        # it -> net effect: no transport write, explicit error.
        token = offline_test_token(base_url=TESTNET_REST)
        with self.assertRaises(TransportWriteAuthorityError):
            self.exchange.place_order(
                {"product_id": 84, "size": 1}, authority=token)
        self.assertEqual(self.transport.calls, [])

    def test_missing_authority_refused_at_adapter(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        exchange = DeltaExchange(api_key="canary-key",
                                 api_secret="canary-secret",
                                 rest=rest)
        with self.assertRaises(TransportWriteAuthorityError):
            exchange.place_order({"product_id": 84, "size": 1})
        with self.assertRaises(TransportWriteAuthorityError):
            exchange.cancel_order(123, product_id=84)
        self.assertEqual(transport.write_calls, [])

    def test_legacy_double_keeps_legacy_signature(self):
        legacy = _LegacyRestDouble()
        exchange = DeltaExchange(api_key="canary-key",
                                 api_secret="canary-secret",
                                 rest=legacy)
        token = offline_test_token(base_url=TESTNET_REST)
        result = exchange.place_order(
            {"product_id": 84, "size": 1}, authority=token)
        self.assertEqual(result, {"success": True})
        self.assertEqual(legacy.calls[0],
                         ("post", "/v2/orders",
                          {"product_id": 84, "size": 1}))

    def test_cancel_requires_product_scope(self):
        with self.assertRaises(ValueError):
            self.exchange.cancel_order(
                123, authority=self._armed_token())
        self.assertEqual(self.transport.calls, [])


class TestRefusalsAtTheBoundary(unittest.TestCase):

    def _transport_rest(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        return transport, rest

    def test_missing_token_refused(self):
        transport, rest = self._transport_rest()
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            rest.post("/v2/orders", payload={"size": 1})
        self.assertIn("no write authority", str(ctx.exception))
        self.assertEqual(transport.write_calls, [])

    def test_offline_kind_refused_at_rest_boundary(self):
        transport, rest = self._transport_rest()
        token = offline_test_token(base_url=TESTNET_REST)
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            rest.post("/v2/orders", payload={"size": 1},
                      authority=token)
        self.assertIn("OFFLINE_TEST", str(ctx.exception))
        self.assertEqual(transport.write_calls, [])

    def test_forged_foreign_mint_refused(self):
        with self.assertRaises(TransportWriteAuthorityError):
            WriteAuthorityToken(mint="not-the-process-mint",
                                kind=KIND_TESTNET_EXPERIMENT,
                                base_url=TESTNET_REST,
                                endpoint="/v2/orders")
        transport, rest = self._transport_rest()
        with self.assertRaises(TransportWriteAuthorityError):
            rest.post("/v2/orders", payload={"size": 1},
                      authority=None)
        self.assertEqual(transport.write_calls, [])

    def test_wrong_kind_for_boundary_refused(self):
        transport, rest = self._transport_rest()
        token = offline_test_token(base_url=TESTNET_REST)
        # the offline OFFLINE_TEST kind is accepted only by an
        # OFFLINE_TEST-only boundary (unit fixtures); every production
        # boundary (REST_WRITE_KINDS, adapter ALL-KINDS sets) refuses
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            require_write_authority(
                token, base_url=TESTNET_REST, endpoint="/v2/orders",
                kinds=REST_WRITE_KINDS)
        self.assertIn("OFFLINE_TEST", str(ctx.exception))
        require_write_authority(
            token, base_url=TESTNET_REST, endpoint="/v2/orders",
            kinds=frozenset({KIND_OFFLINE_TEST}))
        self.assertEqual(transport.write_calls, [])

    def test_wrong_endpoint_refused(self):
        transport, rest = self._transport_rest()
        token = offline_test_token(base_url=TESTNET_REST,
                                   endpoint="/v2/orders")
        require_write_authority(
            token, base_url=TESTNET_REST, endpoint="/v2/orders",
            kinds=frozenset({KIND_OFFLINE_TEST}))
        with self.assertRaises(TransportWriteAuthorityError):
            require_write_authority(
                token, base_url=TESTNET_REST, endpoint="/v2/positions",
                kinds=frozenset({KIND_OFFLINE_TEST}))
        self.assertEqual(transport.write_calls, [])

    def test_wrong_base_url_refused(self):
        transport, rest = self._transport_rest()
        token = offline_test_token(base_url=TESTNET_REST,
                                   endpoint="/v2/orders")
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            require_write_authority(
                token, base_url="https://api.delta.exchange",
                endpoint="/v2/orders",
                kinds=frozenset({KIND_OFFLINE_TEST}))
        self.assertIn("armed for endpoint host", str(ctx.exception))
        self.assertEqual(transport.write_calls, [])


class TestArmedDecisionMintsBoundedAuthority(unittest.TestCase):

    def setUp(self):
        self.h = _Harness(APPROVED_CONTENT)

    def tearDown(self):
        self.h.cleanup()

    def _reserve(self):
        return _reserve_order_for_test(self.h.gate, self.h.record)

    def _post_payload(self):
        return {
            "product_id": 84, "size": "1", "side": "buy",
            "limit_price": "80000", "post_only": True,
            "client_order_id": "P193B-ORDER-01",
        }

    def test_approved_preflight_is_diagnostic_reservation_is_armed(self):
        preflight = self.h.gate.evaluate_preflight(
            auth_record=self.h.record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1),
            limit_price=Decimal("80000"), post_only=True)
        self.assertTrue(preflight.authorized)
        self.assertFalse(preflight.is_armed())
        decision = self._reserve()
        self.assertTrue(decision.is_armed())
        self.assertEqual(decision.reasons, [])

    def test_armed_token_binding_is_testnet_and_orders(self):
        decision = self._reserve()
        payload = self._post_payload()
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=payload)
        self.assertEqual(token.kind, KIND_TESTNET_EXPERIMENT)
        self.assertEqual(token.base_url, TESTNET_REST)
        self.assertEqual(token.endpoint, "/v2/orders")
        validated = require_write_authority(
            token, base_url=TESTNET_REST, endpoint="/v2/orders",
            kinds=REST_WRITE_KINDS, payload=payload)
        self.assertIs(validated, token)

    def test_armed_token_performs_exactly_the_bounded_writes(self):
        transport = _RecordingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self._reserve()
        order_payload = self._post_payload()
        post_token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=order_payload)
        rest.post("/v2/orders", payload=order_payload, authority=post_token)
        cancel_payload = {"id": 123, "product_id": 84}
        cancel_token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=cancel_payload,
            method="DELETE")
        rest.delete("/v2/orders", payload=cancel_payload,
                    authority=cancel_token)
        self.assertEqual([call[0] for call in transport.calls], ["post", "delete"])

    def test_armed_testnet_authority_cannot_ride_a_live_host(self):
        decision = self._reserve()
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=self._post_payload())
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url="https://api.delta.exchange")
        rest.client = transport
        with self.assertRaises(TransportWriteAuthorityError):
            rest.post("/v2/orders", payload=self._post_payload(), authority=token)
        self.assertEqual(transport.write_calls, [])

    def test_order_authority_cannot_be_reused_for_delete_method(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self._reserve()
        payload = self._post_payload()
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=payload)
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            rest.delete("/v2/orders", payload=payload, authority=token)
        self.assertIn("HTTP method POST, not DELETE", str(ctx.exception))
        self.assertEqual(transport.write_calls, [])

    def test_cancel_authority_cannot_be_reused_for_post_method(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self._reserve()
        payload = {"id": 123, "product_id": 84}
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=payload, method="DELETE")
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            rest.post("/v2/orders", payload=payload, authority=token)
        self.assertIn("HTTP method DELETE, not POST", str(ctx.exception))
        self.assertEqual(transport.write_calls, [])

    def test_malformed_order_payload_cannot_be_armed(self):
        decision = self._reserve()
        with self.assertRaises(TransportWriteAuthorityError) as ctx:
            token_for_testnet_experiment(
                decision, base_url=TESTNET_REST,
                payload={"product_id": 84, "side": "buy",
                         "limit_price": "80000", "post_only": True,
                         "client_order_id": "P193B-ORDER-01"})
        self.assertIn("missing required fields: size", str(ctx.exception))

    def test_payload_mismatch_refused_before_transport_write(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self._reserve()
        authorized_payload = self._post_payload()
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=authorized_payload)
        with self.assertRaises(TransportWriteAuthorityError):
            rest.post("/v2/orders", payload={
                "product_id": 1699, "size": 100, "side": "sell",
                "limit_price": "1", "post_only": False,
                "client_order_id": "P193B-ORDER-01",
            }, authority=token)
        self.assertEqual(transport.write_calls, [])

    def test_token_mint_rejects_payload_outside_preflight_scope(self):
        decision = self._reserve()
        with self.assertRaises(TransportWriteAuthorityError):
            token_for_testnet_experiment(
                decision, base_url=TESTNET_REST,
                payload={
                    "product_id": 1699, "size": 100, "side": "sell",
                    "limit_price": "1", "post_only": False,
                    "client_order_id": "P193B-ORDER-01",
                })

    def test_authority_token_cannot_be_replayed(self):
        transport = _RecordingTransport()
        rest = DeltaSignedREST(api_key="canary-key", api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        decision = self._reserve()
        payload = self._post_payload()
        token = token_for_testnet_experiment(
            decision, base_url=TESTNET_REST, payload=payload)
        rest.post("/v2/orders", payload=payload, authority=token)
        with self.assertRaises(TransportWriteAuthorityError):
            rest.post("/v2/orders", payload=payload, authority=token)
        self.assertEqual([call[0] for call in transport.calls], ["post"])

    def test_out_of_scope_instrument_refused(self):
        decision = self.h.gate.evaluate_preflight(
            auth_record=self.h.record, rest_url=TESTNET_REST,
            symbol="ETHUSD", product_id=1699,
            order_size_contracts=Decimal(1), post_only=True)
        self.assertFalse(decision.is_armed())
        self.assertTrue(any("ETHUSD" in reason for reason in decision.reasons))
        self.assertTrue(any("1699" in reason for reason in decision.reasons))


class _FlowTransport:
    """Offline script-flow transport: serves the bounded experiment's
    read pre-checks and records every POST/DELETE (exploding optional).
    """

    def __init__(self):
        self.posts = []
        self.deletes = []

    def get(self, url, headers=None, params=None):
        if "/v2/products" in url:
            return _FakeResponse({"result": [_PRODUCTS_ROW]})
        if "/v2/positions" in url:
            return _FakeResponse({"result": {"size": "0"}})
        if "/v2/orders/" in url:
            # first poll of either experiment reports the order FILLED
            # so no polling sleep is ever executed
            return _FakeResponse({"result": {"state": "filled"}})
        if "/v2/orders" in url:
            return _FakeResponse({"result": []})
        if "/v2/fills" in url:
            return _FakeResponse({"result": []})
        return _FakeResponse({})

    def post(self, url, content=None, headers=None):
        self.posts.append((url, (content or b"").decode("utf-8")))
        return _FakeResponse({"result": {"id": "101",
                                         "state": "resting"}})

    def delete(self, url, content=None, headers=None):
        self.deletes.append((url, (content or b"").decode("utf-8")))
        return _FakeResponse({"success": True})


_INJECTED = {"transport": None}


class _InjectedTransportREST(DeltaSignedREST):
    """DeltaSignedREST whose httpx client is swapped for the offline
    fake immediately after construction (client injection after init
    mirrors the established harness convention)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = _INJECTED["transport"]
        if t is not None:
            self.client = t


def _patch_script_env():
    """Common patches for script-level offline tests: endpoint validator
    no-op, offline httpx book, synthetic-only credentials."""
    def fake_book_get(url, params=None, timeout=None, **kw):
        if "ETHUSD" in str(url):
            return _FakeResponse(dict(_ETH_TOUCH_BOOK))
        return _FakeResponse(dict(_TOUCH_BOOK))

    return [
        mock.patch("research.economics.delta_environment.validate_endpoints",
                   lambda *a, **k: None),
        mock.patch.object(httpx, "get", fake_book_get),
        mock.patch.dict(os.environ, {
            "DELTA_INDIA_TESTNET_API_KEY": "canary-key",
            "DELTA_INDIA_TESTNET_API_SECRET": "canary-secret",
        }),
    ]


class _TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.jsonl"
        self.outdir = Path(self.tmp.name) / "out"
        self.outdir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        _INJECTED["transport"] = None
        self.tmp.cleanup()

    def _canary_doc(self, name="canary.md"):
        path = Path(self.tmp.name) / name
        path.write_text(APPROVED_CONTENT, encoding="utf-8")
        return path


class TestDeriveMakerPricesOffline(_TempDirCase):
    """Case 6 (insane book -> refuse) + Case 11 (buy@bid, sell@ask)."""

    def test_buy_at_bid_and_sell_at_ask(self):
        buy_px, sell_px = exp.derive_maker_leg_prices(50000.5, 50010.0, 0.1)
        self.assertEqual(buy_px, 50000.5)
        self.assertEqual(sell_px, 50010.0)

    def test_misaligned_touch_floors_and_ceils_into_ticks(self):
        buy_px, sell_px = exp.derive_maker_leg_prices(50000.44, 50010.02, 0.1)
        self.assertAlmostEqual(buy_px, 50000.4, places=6)
        self.assertAlmostEqual(sell_px, 50010.1, places=6)

    def test_crossed_book_refused(self):
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(50010.0, 50000.5, 0.1)

    def test_locked_book_refused(self):
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(50000.5, 50000.5, 0.1)

    def test_non_positive_book_refused(self):
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(-1.0, 1.0, 0.1)
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(0.0, 1.0, 0.1)

    def test_degenerate_tick_refused(self):
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(50000.0, 50001.0, 0.0)
        with self.assertRaises(ValueError):
            exp.derive_maker_leg_prices(50000.0, 50001.0, -0.1)


class TestScriptAuthDocFailClosed(_TempDirCase):
    """Cases 1-3: missing / pending / malformed authorization -> exit 2
    with zero transport writes and zero gate ledger side effects."""

    def _run(self, body=None, missing=False):
        doc = Path(self.tmp.name) / "doc.md"
        if missing:
            doc = Path(self.tmp.name) / "absent.md"
        else:
            doc.write_text(body, encoding="utf-8")
        try:
            _INJECTED["transport"] = _FlowTransport()
            with mock.patch(
                    "core.exchanges.delta.delta_auth.DeltaSignedREST",
                    _InjectedTransportREST), \
                    mock.patch.object(exp, "CAPTURE_ID", "test-run"):
                return exp.main([
                    "--execute",
                    "--auth-doc", str(doc),
                    "--ledger-path", str(self.ledger),
                    "--output-dir", str(self.outdir),
                ])
        finally:
            _INJECTED["transport"] = None

    def test_missing_authorization_document(self):
        code = self._run(missing=True)
        self.assertEqual(code, 2)
        self.assertFalse(self.ledger.exists())

    def test_pending_authorization_document(self):
        code = self._run(body=PENDING_CONTENT)
        self.assertEqual(code, 2)
        self.assertFalse(self.ledger.exists())

    def test_malformed_authorization_document(self):
        malformed = ("# TESTNET ORDER EXPERIMENT AUTHORIZATION\n"
                     "- **Authorization ID**: P193B-NOSIG-002\n")
        code = self._run(body=malformed)
        self.assertEqual(code, 2)
        self.assertFalse(self.ledger.exists())


class TestScriptPerLegAuthorization(_TempDirCase):
    """Case 10 + per-leg reservation durability: with the leg-1 terminal
    registration suppressed, leg 2's preflight sees a single open order
    and its write is not attempted (exactly 1 POST, 0 DELETE)."""

    def _flow(self, suppress_terminal):
        patches = _patch_script_env()
        patches.append(mock.patch(
            "core.exchanges.delta.delta_auth.DeltaSignedREST",
            _InjectedTransportREST))
        if suppress_terminal:
            from core.execution import (
                testnet_authorization_gate as _tag)
            patches.append(mock.patch.object(
                _tag.TestnetAuthorizationGate,
                "register_order_terminal",
                lambda *a, **k: None))
        transport = _FlowTransport()
        _INJECTED["transport"] = transport
        try:
            with mock.patch.object(exp, "CAPTURE_ID", "test-capture"), \
                    mock.patch("builtins.print", lambda *a, **k: None):
                for p in patches:
                    p.start()
                try:
                    code = exp.main([
                        "--execute",
                        "--auth-doc", str(self._canary_doc()),
                        "--ledger-path", str(self.ledger),
                        "--output-dir", str(self.outdir),
                    ])
                finally:
                    for p in patches:
                        p.stop()
        finally:
            _INJECTED["transport"] = None
        report = json.loads(
            (self.outdir / "order_experiment_report.json")
            .read_text(encoding="utf-8"))
        ledger_lines = []
        if self.ledger.exists():
            ledger_lines = [l for l in
                            self.ledger.read_text(encoding="utf-8")
                            .splitlines() if l.strip()]
        return code, transport, report, ledger_lines

    def test_second_leg_refused_by_single_open_order(self):
        code, transport, report, ledger_lines = self._flow(
            suppress_terminal=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(transport.deletes, [])
        steps = [s.get("step") for s in report["steps"]]
        self.assertIn("leg_preflight_refused", steps)
        self.assertIn("Single-open-order limit reached",
                      json.dumps(report["steps"]))
        # durable reservations: leg 1 is RESERVED+SUBMITTED on the ledger
        self.assertEqual(len(ledger_lines), 2)
        events = [json.loads(l)["event"] for l in ledger_lines]
        self.assertEqual(events,
                         ["ORDER_RESERVED", "ORDER_SUBMITTED"])

    def test_post_only_payload_at_the_touch(self):
        code, transport, report, _ = self._flow(suppress_terminal=False)
        self.assertEqual(code, 0)
        # both legs placed because the fake venue fills each instantly
        self.assertEqual(len(transport.posts), 2)
        body = transport.posts[0][1]
        payload = json.loads(body)
        self.assertEqual(payload["product_id"], 84)
        self.assertTrue(payload["post_only"])
        self.assertEqual(payload["client_order_id"],
                         "QE-test-capture-1")
        self.assertEqual(payload["limit_price"], "50000.5")
        self.assertEqual(
            json.loads(transport.posts[1][1])["limit_price"], "50010.0")


class TestReconciledDoLegsOffline(_TempDirCase):
    """B-script: incomplete book input fails closed with zero writes;
    a complete flow places both legs through per-leg reservations."""

    def test_missing_book_fails_closed_without_writes(self):
        h = _Harness(APPROVED_CONTENT)
        try:
            rest = DeltaSignedREST(api_key="canary-key",
                                   api_secret="canary-secret",
                                   base_url=TESTNET_REST)
            transport = _ExplodingTransport()
            rest.client = transport
            with mock.patch.object(httpx, "get",
                                   lambda *a, **k: _FakeResponse({})):
                with self.assertRaises(RuntimeError) as ctx:
                    recon.do_legs(rest, h.gate, h.record, 84,
                                  50000.5, 50010.0)
            self.assertIn("fresh touch read failed", str(ctx.exception))
            self.assertEqual(transport.write_calls, [])
        finally:
            h.cleanup()

    def test_bounded_flow_places_both_legs(self):
        h = _Harness(APPROVED_CONTENT)
        try:
            transport = _FlowTransport()
            rest = DeltaSignedREST(api_key="canary-key",
                                   api_secret="canary-secret",
                                   base_url=TESTNET_REST)
            rest.client = transport
            with mock.patch.object(
                    httpx, "get",
                    lambda *a, **k: _FakeResponse(dict(_TOUCH_BOOK))), \
                    mock.patch.object(exp, "CAPTURE_ID", "recon-test"):
                legs = recon.do_legs(rest, h.gate, h.record, 84,
                                     50000.5, 50010.0)
            self.assertEqual(len(legs), 2)
            self.assertTrue(all(l["filled"] for l in legs))
            self.assertEqual([c[0] for c in transport.posts],
                             ["/v2/orders", "/v2/orders"])
            self.assertEqual(
                json.loads(transport.posts[0][1])["limit_price"],
                "50000.5")
            self.assertEqual(
                json.loads(transport.posts[1][1])["limit_price"],
                "50010.0")
        finally:
            h.cleanup()

    def test_leg_preflight_refusal_blocks_the_write(self):
        h = _Harness(APPROVED_CONTENT)
        try:
            # put the gate into a state that arms leg 1 but refuses leg
            # 2 (single open order): suppress terminal registration.
            transport = _FlowTransport()
            rest = DeltaSignedREST(api_key="canary-key",
                                   api_secret="canary-secret",
                                   base_url=TESTNET_REST)
            rest.client = transport
            placed_records = []
            with mock.patch.object(httpx, "get",
                                   lambda *a, **k:
                                   _FakeResponse(dict(_TOUCH_BOOK))), \
                    mock.patch.object(h.gate, "register_order_terminal",
                                      lambda *a, **k: None), \
                    mock.patch.object(exp, "CAPTURE_ID", "recon-test"):
                with self.assertRaises(RuntimeError) as ctx:
                    recon.do_legs(rest, h.gate, h.record, 84,
                                  50000.5, 50010.0,
                                  placed_records=placed_records)
            self.assertIn("Single-open-order limit reached",
                          str(ctx.exception))
            self.assertEqual(len(transport.posts), 1)
            # A second-leg failure must not erase ownership of the first
            # acknowledged order; the caller can now attempt bounded cleanup.
            self.assertEqual(len(placed_records), 1)
            self.assertEqual(placed_records[0]["order_id"], "101")
            self.assertEqual(placed_records[0]["client_order_id"],
                             "QE-recon-test-R1")
            self.assertIsNotNone(placed_records[0]["decision"])
        finally:
            h.cleanup()


class TestFundingSettlementScopeIncompatible(_TempDirCase):
    """Workstream C: ETHUSD/1699 under the BTCUSD/84 authorization
    refuses deterministically (AUTHORIZATION_INCOMPATIBLE) with zero
    transport writes."""

    def test_eth_scope_refusal_zero_writes(self):
        patches = _patch_script_env()
        patches.append(mock.patch(
            "core.exchanges.delta.delta_auth.DeltaSignedREST",
            _InjectedTransportREST))
        # funding main loads the operator's .env via dotenv; keep the
        # test environment canary-only by neutralizing it.
        patches.append(mock.patch(
            "dotenv.load_dotenv", lambda *a, **k: False))
        patches.append(mock.patch.object(
            funding, "LOG",
            Path(self.tmp.name) / "funding_log.jsonl"))
        transport = _FlowTransport()
        _INJECTED["transport"] = transport
        try:
            with mock.patch("builtins.print", lambda *a, **k: None):
                for p in patches:
                    p.start()
                try:
                    code = funding.main([
                        "--execute",
                        "--auth-doc", str(self._canary_doc()),
                        "--ledger-path", str(self.ledger),
                    ])
                finally:
                    for p in patches:
                        p.stop()
        finally:
            _INJECTED["transport"] = None
        self.assertEqual(code, 2)
        self.assertEqual(transport.posts, [])
        self.assertEqual(transport.deletes, [])
        log_text = (Path(self.tmp.name) / "funding_log.jsonl").read_text(
            encoding="utf-8")
        self.assertIn("AUTHORIZATION_INCOMPATIBLE", log_text)


class TestScopeCapEnforcement(_TempDirCase):
    """Case 12 + 14: sizing, post-only, loss budget, cumulative ledger
    cap at 20, boundary at 19, and duplicate/plus-open-order refusals."""

    def _gate(self, ledger=None, content=None):
        ledger = ledger or self.ledger
        gate = TestnetAuthorizationGate(ledger_path=ledger)
        record = gate.parse_authorization_document(
            content if content is not None else APPROVED_CONTENT)
        return gate, record

    def _preflight(self, gate, record, size=Decimal(1),
                   post_only=True, loss=Decimal("0.0"),
                   symbol="BTCUSD", product=84):
        return gate.evaluate_preflight(
            auth_record=record, rest_url=TESTNET_REST,
            symbol=symbol, product_id=product,
            order_size_contracts=size, post_only=post_only,
            limit_price=Decimal("80000"),
            cumulative_realized_loss=loss)

    def test_oversized_order_refused(self):
        gate, record = self._gate()
        d = self._preflight(gate, record, size=Decimal(2))
        self.assertFalse(d.is_armed())
        self.assertTrue(any("exceeds maximum authorized" in r
                            for r in d.reasons))

    def test_post_only_removed_refused(self):
        gate, record = self._gate()
        d = self._preflight(gate, record, post_only=False)
        self.assertFalse(d.is_armed())
        self.assertTrue(any("Post-only is mandatory" in r
                            for r in d.reasons))

    def test_loss_budget_exhausted_refused(self):
        gate, record = self._gate()
        d = self._preflight(gate, record, loss=Decimal("6.00"))
        self.assertFalse(d.is_armed())
        self.assertTrue(any("exhausted authorized budget" in r
                            for r in d.reasons))

    def _seed(self, n):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as f:
            for i in range(n):
                rec = {"timestamp_utc": 1e9, "event": "ORDER_RESERVED",
                       "data": {"cl_ord_id": "seed-%03d" % i}}
                f.write(json.dumps(rec, sort_keys=True) + "\n")

    def test_cumulative_cap_at_20_refused(self):
        self._seed(20)
        gate, record = self._gate()
        d = self._preflight(gate, record)
        self.assertFalse(d.is_armed())
        self.assertTrue(any("Cumulative experiment order limit" in r
                            for r in d.reasons))

    def test_cumulative_boundary_19_still_authorizes_preflight(self):
        self._seed(19)
        gate, record = self._gate()
        d = self._preflight(gate, record)
        self.assertTrue(d.authorized)
        self.assertFalse(d.is_armed())
        self.assertEqual(d.cumulative_orders_placed, 19)

    def test_duplicate_cl_ord_retry_refused(self):
        from core.execution.testnet_authorization_gate import (
            OrderLifecycleState)
        gate, record = self._gate()
        d1 = gate.check_and_reserve_order(
            auth_record=record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1), cl_ord_id="dup-1",
            order_details={"side": "buy", "limit_price": "80000",
                           "post_only": True},
            post_only=True)
        self.assertTrue(d1.is_armed())
        # While the reservation is still active (looks open), the retry
        # is refused fail-closed by the single-open-order constraint.
        d2 = gate.check_and_reserve_order(
            auth_record=record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1), cl_ord_id="dup-1",
            order_details={"side": "buy", "limit_price": "80000",
                           "post_only": True},
            post_only=True)
        self.assertFalse(d2.is_armed())
        self.assertTrue(any("Single-open-order limit reached" in r or
                            "Duplicate cl_ord_id" in r
                            for r in d2.reasons))
        # After the order reaches a terminal state, the same cl_ord_id
        # is permanently burned: the ledger history still owns it.
        gate.register_order_terminal("dup-1",
                                     OrderLifecycleState.FILLED)
        d3 = gate.check_and_reserve_order(
            auth_record=record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1), cl_ord_id="dup-1",
            order_details={"side": "buy", "limit_price": "80000",
                           "post_only": True},
            post_only=True)
        self.assertFalse(d3.is_armed())
        self.assertTrue(any("Duplicate cl_ord_id" in r
                            for r in d3.reasons))
        # exactly one durable reservation, and no duplicate submission
        # record, despite the retries
        rows = [l for l in self.ledger.read_text(encoding="utf-8")
                .splitlines() if l.strip()]
        events = [json.loads(l)["event"] for l in rows]
        self.assertEqual(events.count("ORDER_RESERVED"), 1)
        self.assertNotIn("ORDER_SUBMITTED", events)
        self.assertNotIn("ORDER_PLACED", events)

    def test_second_concurrent_open_order_refused_at_gate(self):
        gate, record = self._gate()
        d1 = gate.check_and_reserve_order(
            auth_record=record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1), cl_ord_id="open-1",
            order_details={"side": "buy", "limit_price": "80000",
                           "post_only": True},
            post_only=True)
        self.assertTrue(d1.is_armed())
        open_before = gate.evaluate_preflight(
            auth_record=record, rest_url=TESTNET_REST,
            symbol="BTCUSD", product_id=84,
            order_size_contracts=Decimal(1), post_only=True)
        self.assertFalse(open_before.is_armed())
        self.assertTrue(any("Single-open-order limit reached" in r
                            for r in open_before.reasons))


class TestPhase10WriteBoundaryComplements(unittest.TestCase):
    """Phase 10 Workstream F complements.

    Adds explicit pins the Phase193B suite did not carry, without
    weakening any existing assertion:
      1. the PRODUCTION transport default enforces write authority;
      2. reads and writes are distinct on one enforced transport
         (GET needs no token; POST/DELETE need an armed token);
      3. gate-dependency failure (None / fabricated / hand-built
         safety decisions) can neither mint a LIVE_SAFETY token
         nor reach the transport (zero writes);
      4. authority refusals never echo the credential canaries.
    """

    def test_production_transport_default_enforces_write_authority(self):
        from core.exchanges.delta.delta_auth import REST_WRITE_KINDS
        from core.exchanges.delta.write_authority import (
            KIND_LIVE_SAFETY,
            KIND_OFFLINE_TEST,
            KIND_TESTNET_EXPERIMENT,
        )
        rest = DeltaSignedREST(api_key="", api_secret="")
        self.assertTrue(rest.enforce_write_authority)
        self.assertIn(KIND_LIVE_SAFETY, REST_WRITE_KINDS)
        self.assertIn(KIND_TESTNET_EXPERIMENT, REST_WRITE_KINDS)
        self.assertNotIn(KIND_OFFLINE_TEST, REST_WRITE_KINDS)

    def test_reads_need_no_token_writes_need_one_same_transport(self):
        transport = _RecordingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        data = rest.get("/v2/orders/1")
        self.assertEqual(data, {})
        for call in (
            lambda: rest.post("/v2/orders", payload={"product_id": 84}),
            lambda: rest.delete(
                "/v2/orders", payload={"id": 1, "product_id": 84}),
        ):
            with self.assertRaises(TransportWriteAuthorityError):
                call()
        self.assertEqual(transport.calls, [])

    def test_gate_dependency_failure_arms_zero_live_writes(self):
        from core.exchanges.delta.write_authority import (
            token_for_live_safety as _mint_live,
        )
        from core.execution.live_safety_gate import (
            LiveBlockedError,
            SafetyDecision,
        )
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        fabricated = SafetyDecision(
            allowed=True, mode="LIVE", reason="hand-built canary",
            allow_live=True, live_execute=True, has_credentials=True)
        for bad_decision in (None, object(), fabricated):
            with self.assertRaises(LiveBlockedError):
                _mint_live(bad_decision, base_url=TESTNET_REST, payload={"size": 1})
            with self.assertRaises(TransportWriteAuthorityError):
                rest.post(
                    "/v2/orders", payload={"size": 1},
                    authority=bad_decision)
            with self.assertRaises(TransportWriteAuthorityError):
                rest.delete(
                    "/v2/orders", payload={"id": 1, "product_id": 84},
                    authority=bad_decision)
        self.assertEqual(transport.write_calls, [])

    def _canary_rest(self):
        transport = _ExplodingTransport()
        rest = DeltaSignedREST(api_key="canary-key",
                               api_secret="canary-secret",
                               base_url=TESTNET_REST)
        rest.client = transport
        return transport, rest

    def test_authority_refusals_do_not_echo_credentials(self):
        _, rest = self._canary_rest()
        with self.assertRaises(TransportWriteAuthorityError) as caught:
            rest.post("/v2/orders", payload={"product_id": 84})
        self.assertNotIn("canary-key", str(caught.exception))
        self.assertNotIn("canary-secret", str(caught.exception))
        self.assertNotIn("WriteAuthorityToken(", str(caught.exception))

class TestCleanupOwnershipFailClosed(_TempDirCase):
    def test_cleanup_refuses_cancel_when_exchange_client_id_mismatches(self):
        class Rest:
            base_url = TESTNET_REST
            def __init__(self):
                self.deletes = []
            def get(self, path, params=None):
                if path == "/v2/orders":
                    return {"result": [{"id": 9001, "product_id": 84,
                                         "state": "open",
                                         "client_order_id": "QE-other-run"}]}
                if path == "/v2/orders/9001":
                    return {"result": {"id": 9001, "product_id": 84,
                                        "state": "open",
                                        "client_order_id": "QE-other-run"}}
                if path == "/v2/positions":
                    return {"result": {"size": 0}}
                raise AssertionError("unexpected GET path: %s" % path)
            def delete(self, path, payload=None, authority=None):
                self.deletes.append((path, payload, authority))
                return {"success": True}
        rest = Rest()
        result = exp._cleanup(rest, 84, [{
            "order_id": "9001", "client_order_id": "QE-this-run-R1",
            "product_id": 84, "decision": None,
        }])
        self.assertEqual(rest.deletes, [])
        self.assertEqual(result["ownership_unverified"], ["9001"])
        self.assertEqual(result["cancelled"], [])
