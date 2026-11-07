"""Phase 194: adversarial tests for cryptographic testnet authorization.

All keys and authorizations in this module are synthetic test fixtures.
No exchange adapter or network transport is used.
"""
from __future__ import annotations

import base64
import os
import time
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution.testnet_authorization_gate import (
    AuthorizationState,
    ExperimentScope,
    OperatorAuthorizationRecord,
    sign_authorization_record,
)

TEST_KEY_ENV = "QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY"


def _raw_public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _record(private_key: Ed25519PrivateKey, **changes) -> OperatorAuthorizationRecord:
    now = time.time()
    values = dict(
        authorization_id="PHASE194-SYNTHETIC-001",
        state=AuthorizationState.OPERATOR_APPROVED,
        operator_identity="SYNTHETIC_TEST_OPERATOR",
        signed_timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2)),
        expiry_timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600)),
        scope=ExperimentScope(
            venue="DELTA_INDIA_TESTNET",
            target_rest_url="https://cdn-ind.testnet.deltaex.org",
            target_ws_url="wss://socket-ind.testnet.deltaex.org",
            allowed_symbols={"BTCUSD"},
            allowed_product_ids={84},
            max_cumulative_orders=20,
            max_simultaneous_open_orders=1,
            max_order_size_contracts=Decimal("1.0"),
            max_order_notional_usd=Decimal("100.00"),
            max_loss_budget_usd=Decimal("5.00"),
            max_order_wait_seconds=120.0,
            require_post_only=True,
            forbid_market_conversion=True,
        ),
        document_sha256="a" * 64,
        signature_payload="",
    )
    values.update(changes)
    record = OperatorAuthorizationRecord(**values)
    record.signature_payload = sign_authorization_record(record, private_key)
    return record


def test_valid_signature_and_current_time_window_passes(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    record = _record(private_key)
    assert record.is_currently_valid()


def test_missing_or_malformed_public_key_fails_closed(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    record = _record(private_key)
    monkeypatch.delenv(TEST_KEY_ENV, raising=False)
    assert not record.is_currently_valid()
    monkeypatch.setenv(TEST_KEY_ENV, "not-base64!")
    assert not record.is_currently_valid()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(b"short").decode())
    assert not record.is_currently_valid()


def test_signature_tampering_fails_closed(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    record = _record(private_key, operator_identity="TAMPERED_OPERATOR")
    record.operator_identity = "DIFFERENT_OPERATOR"
    assert not record.is_currently_valid()


def test_scope_widening_invalidates_signature(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    record = _record(private_key)
    record.scope.allowed_symbols.add("ETHUSD")
    assert not record.is_currently_valid()


def test_expired_and_future_dated_records_fail_closed(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    expired = _record(
        private_key,
        signed_timestamp_utc="2026-01-01T00:00:00Z",
        expiry_timestamp_utc="2026-01-02T00:00:00Z",
    )
    assert not expired.is_currently_valid()
    future = _record(
        private_key,
        signed_timestamp_utc="2999-01-01T00:00:00Z",
        expiry_timestamp_utc="2999-01-02T00:00:00Z",
    )
    assert not future.is_currently_valid()


def test_naive_or_invalid_timestamps_fail_closed(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    naive = _record(private_key, signed_timestamp_utc="2026-10-30T00:00:00")
    assert not naive.is_currently_valid()
    invalid = _record(private_key, expiry_timestamp_utc="not-a-timestamp")
    assert not invalid.is_currently_valid()


def test_non_approved_state_fails_even_with_valid_signature(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(TEST_KEY_ENV, base64.b64encode(_raw_public_key(private_key)).decode())
    record = _record(private_key, state=AuthorizationState.PENDING_OPERATOR_APPROVAL)
    assert not record.is_currently_valid()


def test_signing_helper_rejects_wrong_private_key_size():
    record = _record(Ed25519PrivateKey.generate())
    with pytest.raises(ValueError, match="exactly 32 raw bytes"):
        sign_authorization_record(record, b"too-short")
