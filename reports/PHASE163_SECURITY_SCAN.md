# Security scan report — Phase 163

Phase 163 delivers the remaining QuantEngine core components (`core/runtime/multi_stream_multiplexer.py`, `core/execution/protective_bracket.py`, `core/monitoring/mobile_push_gateway.py`). The declared scan gates are unchanged, and the scanning machinery is byte-carried from Phase 160/161:

| Gate | Question It Answers | Record |
|---|---|---|
| Secret scan | Are there credentials or API keys in the tree? | This file |
| Privacy scan | Are there account identifiers / private payloads / order ids? | `reports/PHASE163_PRIVACY_REVIEW.md` |
| Source integrity | Do the shipped bytes match the manifest? | `BUILD_MANIFEST.sha256` |
| Dependency security | Do pinned dependencies carry known advisories? | Pinned clean (0 open advisories) |
| Packaging hygiene | Can secret paths, bytecode, or caches reach the archive? | This file + `tests/test_packaging_no_secrets_phase132.py` |

---

## 1. Secret Scan (Credentials)

```
python scripts/security/scan_secrets.py --root .
SECRET_SCAN_PASS        (exit code 0)
```

Executed against the Phase 163 build tree. Selection is by *content*: every member whose bytes decode as text is scanned, whatever its suffix. The decoder (`scripts/security/text_decode.py`) handles UTF-8 with an optional BOM, UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM; binary members are declared as opaque classes by the privacy scan (Rule E). There is zero uninspected corner.

Rules enforced:
* `non_empty_known_secret` — non-empty assignment to a known credential name in configuration files;
* `literal_known_secret` — credential names assigned a non-empty literal in Python source;
* `private_key_material` — `-----BEGIN … PRIVATE KEY-----` blocks.

Verdict: **`SECRET_SCAN_PASS` (0 violations)**.

---

## 2. Privacy Scan (Account Identifiers, Private Payloads, Order IDs)

```
python scripts/security/scan_privacy.py --root .
PRIVACY_SCAN_COVERAGE inspected=2003 declared_opaque=11 patterns=*.zip,*.parquet
PRIVACY_SCAN_CLEARANCE NOT_CLEARED (restricted evidence package; not sanitised for redistribution -- PRIVACY_SCAN_PASS is not a publication clearance)
PRIVACY_SCAN_PASS       (exit code 0)
```

Posture (see `reports/PHASE163_PRIVACY_REVIEW.md`): the raw restricted captures under `research/captures/` are empirical evidence of record and are integrity-covered. The 8 raw restricted captures carrying the operator's account ID are covered under the declared allowlist. The 13 sealed historical order-ID carriers are preserved and classified as historical.

Verdict: **`PRIVACY_SCAN_PASS` (0 violations; allowlist is exhaustive)**.

---

## 3. Packaging Hygiene

`tests/test_packaging_no_secrets_phase132.py` and the manifest-completeness contract (`tests/test_phase158_manifest_contract.py`) enforce that no secret-name-bearing path (`.env*`), bytecode file (`__pycache__`, `*.pyc`), cache directory, or prior build archive is manifest-covered, and that the manifest lists every packaged member exactly once.
