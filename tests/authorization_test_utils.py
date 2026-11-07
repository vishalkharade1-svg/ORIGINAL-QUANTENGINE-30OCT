"""Synthetic Ed25519 authorization helpers for offline tests only."""
from __future__ import annotations

import base64
import os
import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from core.execution.testnet_authorization_gate import OperatorAuthorizationRecord, sign_authorization_record

# Deterministic, public test-only key. Never use this key for real authorizations.
_TEST_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)


def approve_for_test(record: OperatorAuthorizationRecord) -> OperatorAuthorizationRecord:
    """Refresh fixture timestamps and sign the fixture with a test-only key."""
    now = time.time()
    record.signed_timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2))
    record.expiry_timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600))
    os.environ["QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY"] = base64.b64encode(_TEST_PUBLIC_KEY).decode("ascii")
    record.signature_payload = sign_authorization_record(record, _TEST_PRIVATE_KEY)
    return record


def test_private_key() -> Ed25519PrivateKey:
    """Return the synthetic test key for document-parser tests only."""
    return _TEST_PRIVATE_KEY


def configure_test_verification_key() -> None:
    """Install only the public half of the synthetic test key in process env."""
    os.environ["QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY"] = base64.b64encode(_TEST_PUBLIC_KEY).decode("ascii")


def sign_record_for_test(record: OperatorAuthorizationRecord) -> str:
    """Sign a fully parsed test record using the deterministic test-only key."""
    return sign_authorization_record(record, _TEST_PRIVATE_KEY)
