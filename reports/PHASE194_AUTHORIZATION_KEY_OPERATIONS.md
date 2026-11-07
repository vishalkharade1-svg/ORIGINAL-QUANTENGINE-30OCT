# Phase 194 — Testnet Authorization Key Operations

## Purpose

QuantEngine's dedicated testnet authorization gate now verifies Ed25519 signatures. Merely supplying operator identity text or a non-empty signature string is not sufficient.

## Runtime configuration

Set `QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY` to the base64 encoding of the **32 raw bytes** of the Ed25519 public key approved for the operator workflow. The matching private key must remain outside the QuantEngine repository, `.env`, app bundle, and runtime host wherever practical. Never commit or log private key material.

An empty, malformed, wrong-length, or non-matching public key fails closed. Signature strings use `ed25519:<base64-encoded 64-byte signature>`.

## Signed authorization contents

The signature covers a canonical JSON message containing:

- authorization ID and operator identity;
- signed and expiry timestamps;
- SHA-256 of the authorization document with the `Operator Signature` value blanked;
- complete experiment scope: venue, REST/WS endpoints, symbols, product IDs, cumulative and concurrent order limits, size/notional/loss limits, timeout, post-only requirement, market-conversion prohibition, and book-validity requirement.

Timestamps must be timezone-aware ISO-8601 UTC values. Expiry must be after signing and after the current time; signing more than 60 seconds in the future is rejected. A scope change invalidates the signature.

## Issuance workflow still required

1. The operator-controlled approval process generates or accesses the private key in a protected environment.
2. It constructs the exact authorization record and experiment scope to be used by the gate.
3. It signs the canonical message with Ed25519 and writes the `ed25519:<base64>` signature into the authorization document.
4. QuantEngine receives only the public key and signed authorization document.
5. Offline adversarial tests pass before any bounded testnet write is considered.

The repository's `sign_authorization_record` helper is a primitive for trusted tooling and tests, not a complete operator approval UI, key custody service, revocation service, or production key-management system. Do not treat this document as an issued authorization.

## Current evidence status

- Synthetic cryptographic authorization tests: passed in the focused suite.
- Operator public-key provisioning and real signed authorization: not done.
- Testnet order writes in Phase 194: none performed.
- Full suite: not run; current environment lacks `pyarrow` and has pytest 9.0.2 while the project pins 9.0.3.
- Release gate: **HOLD**.
