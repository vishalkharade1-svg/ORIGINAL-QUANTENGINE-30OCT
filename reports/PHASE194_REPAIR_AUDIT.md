# QuantEngine Phase 194 — Cryptographic Testnet Authorization Hardening

**Date:** 2026-10-30  
**Status:** IMPLEMENTED / FOCUSED TESTED; TESTNET WRITE HOLD  
**Strategy status:** EDGE NOT ESTABLISHED

## Executive result

The testnet authorization gate no longer treats operator name and signature text as proof of approval. `OperatorAuthorizationRecord.is_currently_valid()` now fails closed unless it can verify an Ed25519 signature using `QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY`, parse timezone-aware issue and expiry timestamps, verify the authorization is approved and unexpired, reject issue times more than 60 seconds in the future, and validate the signed message containing the complete configured experiment scope.

The private signing key is not required by the QuantEngine runtime verifier. `.env.example` documents the public-key setting only. The new key-operations document explicitly says the signing helper is not a complete operator approval/key-custody workflow.

## Changes

- `core/execution/testnet_authorization_gate.py`
  - Added strict UTC timestamp parsing.
  - Added canonical scope-bound authorization message serialization.
  - Added Ed25519 signature verification using a base64-encoded 32-byte public key from `QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY`.
  - Added a signing primitive for trusted external tooling and synthetic tests.
  - Changed authorization document hashing to blank the signature value before hashing, avoiding a circular signature/hash dependency.
- `requirements.txt`: pinned `cryptography==46.0.4`.
- `.env.example`: documented the empty public-key configuration setting; no key material included.
- `tests/test_phase194_cryptographic_authorization.py`: synthetic-key adversarial tests for valid signatures, missing/invalid public keys, tampering, scope widening, expiry, future timestamps, naive/invalid timestamps, unapproved state, and invalid signing-key length.
- Existing Phase 189–193A authorization/execution tests now use synthetic signed fixtures; a modified test scope must be re-signed.
- `tests/conftest.py`: makes the shared test-only authorization helper importable without adding production compatibility bypasses.
- `reports/PHASE194_AUTHORIZATION_KEY_OPERATIONS.md`: documents the operator-key boundary and remaining issuance workflow.
- `reports/PHASE194_RELEASE_GATES.json`: records current evidence and blockers.
- `BUILD_MANIFEST.sha256`: regenerated and independently verified after changes.

## Verification results

| Check | Result | Meaning |
|---|---|---|
| Focused Phase 189–194 authorization / ledger / lifecycle / execution-safety suites | **70 passed** | 9 subtests passed; two multiprocessing fork deprecation warnings |
| Test collection | **4,872 collected** | Collection only; not a test-suite pass |
| Build manifest | **PASS — 0 problems** | Current package files match the generated manifest |
| Working-tree secret scan | **PASS** | Does not remediate historical Git credential exposure |
| Dependency pin contract | **BLOCKED / FAIL in this environment** | Current runtime lacks `pyarrow` and has pytest 9.0.2 versus the project pin 9.0.3 |
| Full test suite | **NOT RUN** | Requires a complete supported environment and a batched run |
| Testnet order write | **NOT PERFORMED** | No exchange calls or order writes in this phase |

The focused tests ran under Python 3.13.5 / pytest 9.0.2, not the repository's documented Python 3.12 / pytest 9.0.3 verification environment. Do not treat the focused test result as full release certification.

## Remaining blockers

1. **Operator public-key provisioning:** an operator-controlled workflow must provision `QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY` and issue a genuine signed authorization. The private key must remain outside the repository and runtime service.
2. **Authorization issuance lifecycle:** a full operator approval, revocation, and key-rotation workflow is not implemented by this phase.
3. **Environment:** install/use the pinned, complete Python 3.12 dependency environment (including `pyarrow` and pytest 9.0.3), rerun the dependency contract, then run the full suite in batches.
4. **Credential history:** historical credential exposure remains a separate owner action; rotate/revoke exposed credentials and review account activity. No rotation is claimed here.
5. **Trading evidence:** realistic costs/fills and strategy edge remain unestablished.

## Release decision

**HOLD testnet order writes.** Code-level cryptographic verification and focused regression tests are implemented, but the real operator public key and authorization have not been provisioned, the full suite is not certified, and no testnet order was submitted. Production trading remains prohibited.
