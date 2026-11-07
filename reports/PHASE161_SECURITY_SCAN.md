# Security scan report — Phase 161

Phase 161 is a dependency-environment adoption cycle on top of the sealed
Phase 160 bytes: the three evaluated advisory upgrades are adopted and the
release evidence is re-derived under the adopted pins.  The declared scan gates
are unchanged and the scanning machinery is byte-carried from Phase160; each
gate is re-executed under the adopted environment, not carried over as prose:

| gate | question it answers | record |
|---|---|---|
| secret scan | are there credentials in the tree? | this file |
| privacy scan | are there account identifiers / private payloads / order ids? | `reports/PHASE161_PRIVACY_REVIEW.md` |
| source integrity | do the shipped bytes match the manifest? | `reports/PHASE161_MANIFEST_AUDIT.json` |
| dependency security | do the pinned dependencies carry known advisories, and are they reachable? | `reports/PHASE161_DEPENDENCY_REVIEW.md` |
| packaging hygiene | can a secret-bearing path, bytecode or cache reach the archive? | this file + `tests/test_packaging_no_secrets_phase132.py` |

## 1. Secret scan (credentials)

```
python scripts/security/scan_secrets.py --root .
SECRET_SCAN_PASS        (exit code 0)
```

Executed 2026-10-18 against the Phase 161 build tree, after the environment
adoption.  Selection is by *content*: every member whose bytes decode as text
is scanned, whatever its suffix (the Phase160 closure, carried unchanged).  The
decoder (`scripts/security/text_decode.py`) handles UTF-8 with an optional BOM,
UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM; a member whose bytes
are binary is not scanned as garbage here — it must instead be declared as an
opaque class by the privacy scan (rule E there), or that scan fails.  So there
is no uninspected corner left in this gate: every member is either scanned as
text or visibly declared and enumerated.

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
python scripts/security/scan_privacy.py --root . --json reports/PHASE161_PRIVACY_SCAN.json
PRIVACY_SCAN_CLEARANCE NOT_CLEARED   (restricted evidence package; not
                                      sanitised for redistribution)
PRIVACY_SCAN_PASS       (exit code 0)
```

Same posture as Phase160 (see `reports/PHASE161_PRIVACY_REVIEW.md`): the raw
restricted captures under `research/captures/` are the evidence of record and
are integrity-covered; findings outside them are violations.  The sealed
historical order-id carriers — byte-identical to their Phase157 input-archive
members and unchanged by this cycle — re-classify as historical; they are
enumerated in `reports/PHASE161_PRIVACY_SCAN.json` and were never rewritten.

Phase161 enforcement note: the scanners (`scan_secrets.py`, `scan_privacy.py`)
and the shared decoder (`text_decode.py`) are byte-carried from Phase160 — the
content-decoding boundary closure and rule E coverage stay exactly as closed.
This cycle re-ran them under the adopted environment against the same carried
member set plus this cycle's records; the report schema stays
`quantengine.privacy-scan.v2` with its `content_coverage` block.

## 3. Packaging hygiene (unchanged, tested)

`tests/test_packaging_no_secrets_phase132.py` and the manifest-completeness
contract (`tests/test_phase158_manifest_contract.py`) enforce that no
secret-name-bearing path (`.env*`), bytecode file, cache directory or prior
build archive is manifest-covered, and that the manifest lists every packaged
member exactly once.  The manifest generator still reports a listed-but-absent
file as `missing:` (Phase159 wording fix, carried); no packaging behavior
changed in this phase.
