# Security scan report — Phase 158

Five gates are reported separately here and in the companion records, because a
clean result in one is not a result in another:

| gate | question it answers | record |
|---|---|---|
| secret scan | are there credentials in the tree? | this file |
| privacy scan | are there account identifiers / private payloads / order ids? | `reports/PHASE158_PRIVACY_REVIEW.md` |
| source integrity | do the shipped bytes match the manifest? | `reports/PHASE158_MANIFEST_AUDIT.json` |
| dependency security | do the pinned dependencies carry known advisories, and are they reachable? | `reports/PHASE158_DEPENDENCY_REVIEW.md` |
| packaging hygiene | can a secret-bearing path, bytecode or cache reach the archive? | this file + `tests/test_packaging_no_secrets_phase132.py` |

## 1. Secret scan (credentials)

```
python scripts/security/scan_secrets.py
SECRET_SCAN_PASS        (exit code 0)
```

Rules the scanner actually enforces (read from `scripts/security/scan_secrets.py`,
not from a summary):

* `non_empty_known_secret` — a non-empty assignment to a known credential name
  (`DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_INDIA_TESTNET_*`,
  `DELTA_SANDBOX_*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `OPENROUTER_API_KEY`, `CONTROL_API_TOKEN`, `REMOTE_*_TOKEN`) **in a
  configuration file** (`.env`, `.env.*`, `.ini`, `.toml`, `.yaml`, `.yml`);
* `literal_known_secret` — the same names assigned a non-empty string literal in
  Python source;
* `private_key_material` — a `-----BEGIN … PRIVATE KEY-----` block.

The scanner deliberately scans ignored files (notably `.env`) because
`.gitignore` prevents commits but does not make a workstation credential safe,
and it reports only path, line and rule — never a matched value.

## 2. Privacy scan (account identifiers, private payloads, order ids)

```
python scripts/security/scan_privacy.py --root .
PRIVACY_SCAN_CLEARANCE NOT_CLEARED   (restricted evidence package; not
                                      sanitised for redistribution)
PRIVACY_SCAN_PASS       (exit code 0)
```

Result of the recorded run (`reports/PHASE158_PRIVACY_SCAN.json`):

* account-identifier carriers == the six enumerated raw restricted captures
  exactly (set equality, so the allowlist cannot go stale or be widened);
* 38 distinct raw venue order ids found across 21 capture files;
* **0 new** order-id leakage into `reports/`, `docs/`, `research/results/`;
* 13 **historical** carriers enumerated as notes — sealed experiment journals of
  Phases 114–152, byte-identical to their input-archive members, reported rather
  than rewritten. Full enumeration and reasoning:
  `reports/PHASE158_PRIVACY_REVIEW.md`.
* **Not a publication clearance.** The scan report carries
  `publication_clearance: "NOT_CLEARED"` with a reason: the package ships the
  private captures and the sealed order-id journals deliberately, so
  `PRIVACY_SCAN_PASS` states that the confinement rules hold *inside this
  restricted package* — nothing more. Both gates above are scoped verdicts, not
  permission to redistribute.

## 3. Packaging hygiene

* Forbidden names (`.env`, `.env.test`, `.env.local`), parts (`env/`) and
  suffixes (`.pem`, `.key`, `.secret`) are absent from the packaged tree.
  `.env.example` is present and carries the template only.
* The manifest contract excludes bytecode (`*.pyc`, `*.pyo`), caches
  (`__pycache__`, `.pytest_cache`), virtualenvs, `logs/`, prior build archives
  (`QuantEngine_*.zip`) and the extract working copy. Research evidence ZIPs
  under `research/` **are** covered by the manifest, deliberately.
* `tests/test_packaging_no_secrets_phase132.py` asserts the allowlist rule
  directly, and its scanner-coverage assertion is the same one used here.

### The two live-`.env` guard failures, stated precisely

Two packaging-hygiene tests (`test_packaging_no_secrets_phase132.py` and
`test_stage123_operational.py::…::test_security_scan_no_real_credentials`) fail
when the suite runs **in a worktree that holds a live `.env`** and pass in the
packaged tree, which contains only `.env.example`. That is the assertion working
as designed: the archive must not contain the credential file, and a worktree
that holds one is correctly flagged. They are not weakened, skipped or
special-cased anywhere in Phase158; the extracted-package run is the run to read
for packaging hygiene, and the worktree result is reported as what it is.

## 4. Archive-level scans (final bytes)

This report ships **inside** the archive, so it can only record scans of the
tree that was packed. The scans of the final archive bytes are run after the
build against a fresh extraction and recorded beside the archive:

```
post-build bundle: QuantEngine_PHASE158_POST_BUILD/reports/PHASE158_POST_BUILD_VERIFICATION.json
  - secret scan over the extracted package
  - privacy scan over the extracted package
  - member-by-member verification against BUILD_MANIFEST.sha256
```

Nothing in this archive claims a green result for scans it could not run on
itself; the detached record and the post-build bundle exist precisely because
those facts live outside the archive.

## 5. Negative controls (proof the scanners can fail)

* Secret scanner: rule-level tests exist in the tree's history; the
  packaging-hygiene contract plants forbidden paths in a throwaway tree and
  requires detection.
* Privacy scanner: `tests/test_phase158_privacy_contract.py` proves the
  identifier planted in a report is reported, the identifier inside an
  allowlisted capture is not, a new aggregate file carrying a raw order id is
  **new leakage** (fails), a byte-identical input member is classified
  historical, and an *edited* historical file forfeits that classification and
  fails.
* Manifest verifier: five negative controls (wrong hash, extra file, missing
  file, duplicate line, malformed line) in
  `tests/test_phase158_manifest_contract.py`.

## 6. Findings carried forward

* Three dependency advisories affect pinned versions; two of the three vulnerable
  code paths are unreachable from this tree. Decision and evidence:
  `reports/PHASE158_DEPENDENCY_REVIEW.md`.
* The historical order-id baseline (13 sealed files) is a real privacy property of
  this package: it is a restricted evidence package, not a distributable.
* No credential material was found in the tree, in either scan, at any revision
  of this phase.
