# Security scan report — Phase 162

Phase 162 is an empirical execution and release cycle on top of the sealed Phase 161 bytes. The declared scan gates are unchanged, and the scanning machinery is byte-carried from Phase 160/161:

| gate | question it answers | record |
|---|---|---|
| secret scan | are there credentials in the tree? | this file |
| privacy scan | are there account identifiers / private payloads / order ids? | `reports/PHASE162_PRIVACY_REVIEW.md` |
| source integrity | do the shipped bytes match the manifest? | `reports/PHASE162_MANIFEST_AUDIT.json` |
| dependency security | do the pinned dependencies carry known advisories, and are they reachable? | `reports/PHASE162_DEPENDENCY_REVIEW.md` |
| packaging hygiene | can a secret-bearing path, bytecode or cache reach the archive? | this file + `tests/test_packaging_no_secrets_phase132.py` |

## 1. Secret scan (credentials)

```
python scripts/security/scan_secrets.py --root .
SECRET_SCAN_PASS        (exit code 0)
```

Executed 2026-10-18 against the Phase 162 build tree. Selection is by *content*: every member whose bytes decode as text is scanned, whatever its suffix. The decoder (`scripts/security/text_decode.py`) handles UTF-8 with an optional BOM, UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM; binary members are declared as opaque classes by the privacy scan (rule E there). There is zero uninspected corner: every member is either scanned as text or visibly declared and enumerated.

Rules enforced:
* `non_empty_known_secret` — a non-empty assignment to a known credential name in configuration files;
* `literal_known_secret` — credential names assigned a non-empty literal in Python source;
* `private_key_material` — `-----BEGIN … PRIVATE KEY-----` blocks.

Verdict: **`SECRET_SCAN_PASS` (0 violations)**.

## 2. Privacy scan (account identifiers, private payloads, order ids)

```
python scripts/security/scan_privacy.py --root . --json reports/PHASE162_PRIVACY_SCAN.json
PRIVACY_SCAN_CLEARANCE NOT_CLEARED   (restricted evidence package; not sanitised for redistribution)
PRIVACY_SCAN_PASS       (exit code 0)
```

Posture (see `reports/PHASE162_PRIVACY_REVIEW.md`): the raw restricted captures under `research/captures/` are the evidence of record and are integrity-covered. Phase 162 adds the 2 empirical WebSocket fill captures (`research/captures/phase162_recon/private_ws_archive.json` and `private_ws_frames.json`) to the declared allowlist (now 8 files total). The 13 sealed historical order-id carriers are re-classified as historical and enumerated in `reports/PHASE162_PRIVACY_SCAN.json`.

Verdict: **`PRIVACY_SCAN_PASS` (0 violations; allowlist is exhaustive)**.

## 3. Packaging hygiene

`tests/test_packaging_no_secrets_phase132.py` and the manifest-completeness contract (`tests/test_phase158_manifest_contract.py`) enforce that no secret-name-bearing path (`.env*`), bytecode file, cache directory or prior build archive is manifest-covered, and that the manifest lists every packaged member exactly once.
