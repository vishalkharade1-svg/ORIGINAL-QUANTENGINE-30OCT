# Security scan report — Phase 160

Phase 160 is a scanner-boundary hardening cycle on top of the sealed Phase 159
bytes: it closes the content-decoding boundary the Phase159 vendor-audit handoff
declared.  The declared scan gates are unchanged; each is re-executed against
this tree, not carried over as prose:

| gate | question it answers | record |
|---|---|---|
| secret scan | are there credentials in the tree? | this file |
| privacy scan | are there account identifiers / private payloads / order ids? | `reports/PHASE160_PRIVACY_REVIEW.md` |
| source integrity | do the shipped bytes match the manifest? | `reports/PHASE160_MANIFEST_AUDIT.json` |
| dependency security | do the pinned dependencies carry known advisories, and are they reachable? | `reports/PHASE160_DEPENDENCY_REVIEW.md` |
| packaging hygiene | can a secret-bearing path, bytecode or cache reach the archive? | this file + `tests/test_packaging_no_secrets_phase132.py` |

## 1. Secret scan (credentials)

```
python scripts/security/scan_secrets.py --root .
SECRET_SCAN_PASS        (exit code 0)
```

Executed 2026-10-18 against the Phase 160 build tree.  Selection is by
*content*: every member whose bytes decode as text is scanned, whatever its
suffix.  The decoder (`scripts/security/text_decode.py`) handles UTF-8 with an
optional BOM, UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM; a
member whose bytes are binary is not scanned as garbage here — it must instead
be declared as an opaque class by the privacy scan (rule E there), or that scan
fails.  So there is no uninspected corner left in this gate: every member is
either scanned as text or visibly declared and enumerated.

This closes the boundary the Phase159 vendor-audit handoff declared.  The 12
carried UTF-16LE members (suite logs and tree listings written by Windows
tooling) previously arrived NUL-interleaved and matched no rule, and members
outside the old suffix set were never read at all.  `tests/test_secret_scan_phase0.py`
pins the closure with five regressions: UTF-16 with BOM, BOM-less UTF-16 LE and
BE, UTF-32 with BOM (each fixture asserts its own bytes first), and a binary
member class that must produce no findings rather than bespoke garbage.

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
python scripts/security/scan_privacy.py --root . --json reports/PHASE160_PRIVACY_SCAN.json
PRIVACY_SCAN_CLEARANCE NOT_CLEARED   (restricted evidence package; not
                                      sanitised for redistribution)
PRIVACY_SCAN_PASS       (exit code 0)
```

Same posture as Phase159 (see `reports/PHASE160_PRIVACY_REVIEW.md`): the raw
restricted captures under `research/captures/` are the evidence of record and
are integrity-covered; findings outside them are violations.  The 13 aggregate
carriers carrying historical raw order ids re-classified as historical
(byte-identical to their Phase157 input-archive members) — enumerated in
`reports/PHASE160_PRIVACY_SCAN.json`, never rewritten.

Phase160 enforcement additions: the same content-based decoding for rules A
and B (the UTF-16 boundary closure), and rule E content coverage — every member
is content-inspected or a declared opaque class (`*.zip`, `*.parquet`); an
undeclared binary member fails the scan.  The report schema advances to
`quantengine.privacy-scan.v2` and carries a `content_coverage` block that names
the decoded split and enumerates the 11 declared opaque members (the ten
retained acquisition archives and the one acquisition parquet).

## 3. Packaging hygiene (unchanged, tested)

`tests/test_packaging_no_secrets_phase132.py` and the manifest-completeness
contract (`tests/test_phase158_manifest_contract.py`) enforce that no
secret-name-bearing path (`.env*`), bytecode file, cache directory or prior
build archive is manifest-covered, and that the manifest lists every packaged
exactly once.  The manifest generator still reports a listed-but-absent file
as `missing:` (Phase159 wording fix, carried); no packaging behavior changed in
this phase.
