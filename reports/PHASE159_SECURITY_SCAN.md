# Security scan report — Phase 159

Phase 159 is a hardening-only cycle on top of the sealed revision-2 bytes of the
Phase 158 release-repair build.  The declared scan gates are unchanged; each is
re-executed against this tree, not carried over as prose:

| gate | question it answers | record |
|---|---|---|
| secret scan | are there credentials in the tree? | this file |
| privacy scan | are there account identifiers / private payloads / order ids? | `reports/PHASE159_PRIVACY_REVIEW.md` |
| source integrity | do the shipped bytes match the manifest? | `reports/PHASE159_MANIFEST_AUDIT.json` |
| dependency security | do the pinned dependencies carry known advisories, and are they reachable? | `reports/PHASE159_DEPENDENCY_REVIEW.md` |
| packaging hygiene | can a secret-bearing path, bytecode or cache reach the archive? | this file + `tests/test_packaging_no_secrets_phase132.py` |

## 1. Secret scan (credentials)

```
python scripts/security/scan_secrets.py --root .
SECRET_SCAN_PASS        (exit code 0)
```

Executed 2026-10-17 against the Phase 159 build tree.  The Phase158 revision-2
self-audit observed that a UTF-8 BOM on line 1 of a `.env` file hid the first
line's assignment from the `^`-anchored rules (U+FEFF is not whitespace).  In
this phase the scanner decodes every scannable file with `encoding="utf-8-sig"`,
so a leading BOM is stripped before rule matching and BOM-less files decode
identically.  `tests/test_secret_scan_phase0.py::…::test_bom_prefixed_first_line_secret_is_found`
pins the behavior with a BOM'd fixture whose fixture carries an actual
`\xef\xbb\xbf` prefix (asserted on the bytes, not assumed).

Rules the scanner enforces (read from `scripts/security/scan_secrets.py`, not
from a summary):

* `non_empty_known_secret` — a non-empty assignment to a known credential name
  (`DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_INDIA_TESTNET_*`,
  `DELTA_SANDBOX_*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `OPENROUTER_API_KEY`, `CONTROL_API_TOKEN`, `REMOTE_*_TOKEN`) **in a
  configuration file** (`.env`, `.env.*`, `.ini`, `.toml`, `.yaml`, `.yml`);
* `literal_known_secret` — the same names assigned a non-empty string literal in
  Python source;
* `private_key_material` — a `-----BEGIN … PRIVATE KEY-----` block.

The scanner scans ignored files (notably `.env`) because `.gitignore` prevents
commits but does not make a workstation credential safe, and it reports only
path, line and rule — never a matched value.

## 2. Privacy scan (account identifiers, private payloads, order ids)

```
python scripts/security/scan_privacy.py --root . --json reports/PHASE159_PRIVACY_SCAN.json
PRIVACY_SCAN_CLEARANCE NOT_CLEARED   (restricted evidence package; not
                                      sanitised for redistribution)
PRIVACY_SCAN_PASS       (exit code 0)
```

Same posture as Phase158 (see `reports/PHASE159_PRIVACY_REVIEW.md`): the raw
restricted captures under `research/captures/` are the evidence of record and
are integrity-covered; findings outside them are violations.  The 13 aggregate
carriers carrying historical raw order ids re-classified as historical
(byte-identical to their Phase157 input-archive members) — enumerated in
`reports/PHASE159_PRIVACY_SCAN.json`, never rewritten.  The line reader now
decodes with `utf-8-sig` as well (same BOM hardening as the secret scanner),
pinned by a dedicated regression test.

## 3. Packaging hygiene (unchanged, tested)

`tests/test_packaging_no_secrets_phase132.py` and the manifest-completeness
contract (`tests/test_phase158_manifest_contract.py`) enforce that no
secret-name-bearing path (`.env*`), bytecode file, cache directory or prior
build archive is manifest-covered, and that the manifest lists every packaged
exactly once.  The manifest generator's verifier now reports a listed-but-absent
file as `missing:` (the Phase158 wording `manifest-extra:` read inverted) with
detection unchanged; `tests/test_phase158_manifest_contract.py` pins the label.
