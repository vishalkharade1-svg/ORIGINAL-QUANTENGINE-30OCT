# Build handoff — QuantEngine Phase 158 release-repair candidate

## What was delivered

| Item | Name | Where |
|---|---|---|
| Release candidate | `QuantEngine_PHASE158_RELEASE_CANDIDATE.zip` | beside this tree |
| Detached hash record | `RELEASE_HASH_PHASE158.txt` | beside the archive — **not** inside it |
| Post-build audit (against final bytes) | `PHASE158_SELF_AUDIT.md` | post-build bundle |
| Snapshot audit (what was packed) | `reports/PHASE158_SNAPSHOT_AUDIT.md` | inside the archive |
| Extracted-package run | `PHASE158_EXTRACTED_PACKAGE_TESTS.txt` | post-build bundle |
| Independent-audit prompt | `docs/CLAUDE_PHASE158_INDEPENDENT_AUDIT_PROMPT.md` | inside the archive (16 items) |
| Audit findings and repairs | `reports/PHASE158_AUDIT_REPAIRS.json` | inside the archive (disposition of the revision-1 audit) |

Three artifacts cannot live inside the archive because they describe the archive
itself: the hash record, the self-audit against the final bytes, and the
extracted-package test log. Everything else — reports, triage, scans, gates,
provenance — is inside. The in-archive snapshot audit states its own scope
explicitly so it can never be mistaken for the archive-bytes audit; that naming
split is the deliberate answer to the Phase157 defect where a *stale* self-audit
shipped inside the archive describing a superseded build.

## The archive cannot contain its own hash

No file in the tree embeds the shipped archive's SHA-256;
`tests/test_release_consistency_phase155.py` fails the build if one appears. The
hash lives only in `RELEASE_HASH_PHASE158.txt`, which is also where the member
and byte counts are recorded.

**Verify a delivery:**

```
sha256sum  QuantEngine_PHASE158_RELEASE_CANDIDATE.zip      # == detached record
unzip -q   QuantEngine_PHASE158_RELEASE_CANDIDATE.zip -d extracted
cd extracted
python scripts/generate_manifest.py --root . > /tmp/regen && diff /tmp/regen BUILD_MANIFEST.sha256
python scripts/generate_manifest.py --root . --verify      # MANIFEST_PASS (0 problems)
python -m pytest -q -p no:cacheprovider --tb=short tests/  # see "Test status" below
```

The manifest is LF-only and `generate_manifest.py` writes UTF-8 bytes to both
the file and stdout, so that byte-for-byte comparison holds on any platform
(revision 1 shipped a CRLF manifest; the audit's F-03). Running the suite
leaves the tree manifest-valid: a session snapshot guard (`tests/conftest.py`)
verifies every covered file against the manifest at session start and restores
any rewritten file byte-exactly, so `--verify` still prints
`MANIFEST_PASS (0 problems)` after a full run (the audit's F-02).

## What Phase 158 changed, and why

Phase157 shipped a candidate whose *evidence* contradicted the bytes. Phase158
repaired the tree and made each repair falsifiable:

1. **LF restoration (15 files).** A line-ending conversion (LF→CRLF) happened
   between the `phase11f` mint and Phase131. It broke ten raw-byte pins in
   `research/phase11f/freeze_manifest.json` and five byte-canonical JSON
   artifacts without changing a byte of content. Restoring LF reproduces every
   recorded pin exactly — the hash *is* the proof.
2. **Dataset reconstruction (1 file).** `data/history/BTCUSDT_1m_phase19_extension.json`
   is gitignored by this project's own packaging contract, so it shipped in no
   archive from Phase131 onward and ten tests failed for that reason alone. The
   content is recoverable from `BTCUSDT_1m_oos_topup.json` (its header records
   `prior_received: 11899`; the frozen artifact records the extension's
   `dataset_hash`). The reconstruction is derivation-checked and the file
   carries its own disclosure block. It is *verified content*, not original
   bytes, and says so.
3. **Git-evidence contract.** All 40 Git-dependent facts are gated as
   `BLOCKED_EVIDENCE` through `tests/evidence_mode.py`. Nineteen had been failing
   loudly; **twenty-one had been passing vacuously** — a failed `git` command
   returns empty output, which satisfied assertions such as
   `assertEqual(out, "")`. Two of the vacuous ones are a credential scan and a
   research-byte check. The same guard steps aside in a real repository, and
   that positive control is a test.
4. **Stale evidence, labelled not rewritten.**
   `reports/PHASE157_SELF_AUDIT.md` describes a superseded 1,817-member build;
   its bytes are untouched and `reports/PHASE158_PROVENANCE.json` labels it.
   `reports/RELEASE_PROVENANCE.json` (Phase132 content under a generic name) was
   renamed to `reports/RELEASE_PROVENANCE_PHASE132.json`, bytes unchanged.
5. **Release-record contracts.** New tests fail the build if a required release
   record is missing, if a record names the wrong artifact, if a record
   references a report that does not exist, if a gate is blocked while a
   `PRODUCTION_READY` claim stands, or if a historical record was rewritten.
6. **Privacy and packaging.** The archive is a **restricted evidence package**:
   it deliberately ships raw private captures carrying the operator's account
   identifier and venue order ids (the identifier value itself appears nowhere
   but those captures, and is not repeated in this document).
   `scripts/security/scan_privacy.py` enforces that confinement mechanically,
   and `reports/PHASE158_PRIVACY_REVIEW.md` enumerates the six permitted paths
   with reasons. Originals are byte-identical to their Phase157 members —
   nothing was sanitized or re-captured.
7. **Manifest verifier hardening.** `scripts/generate_manifest.py` now reports
   malformed and duplicate manifest lines instead of silently collapsing them,
   with negative-control tests for every failure mode.
8. **Post-audit authenticity repairs (revision 2).** The independent audit of
   the first build found two defects of one class — platform-dependent bytes.
   `data/runtime/risk_policy_overrides.json` was re-drifted to CRLF by every
   Windows-side save (its Phase131 pin, `a2b9f5c6…`, is LF); it is restored to
   its authentic LF bytes and `core/risk/trading_policy.py` persistence now
   writes LF explicitly, so identical policy state serialises to identical
   bytes everywhere. `BUILD_MANIFEST.sha256` is now LF-only and regenerates
   byte-exactly on every platform. `tests/conftest.py` adds a session snapshot
   guard — a test run can no longer leave a covered file rewritten, and the
   `SNAPSHOT_GUARD_SUMMARY` line reports every event. The findings and their
   dispositions are in `reports/PHASE158_AUDIT_REPAIRS.json`.

## What Phase 158 did NOT change

* **No digest was re-pinned.** The five strategy-digest tests stay red; they are
  correct change detectors (BLOCK-158-01 in `reports/PHASE158_BLOCKERS.json`).
* **No test was weakened, deleted, skipped for convenience, or xfailed.**
* **No order was placed.** Every order-capable script remains behind an explicit
  `--execute`; the funding/repeat-match captures remain externally blocked by the
  operator's IP whitelist.
* **No economic claim advanced.** `EDGE NOT ESTABLISHED` stands.
* **No dataset byte was synthesized.** The reconstruction is a verified
  derivation from data already in the archive, disclosed as such.

## Environment this release was built and tested under

Python 3.12.10; pytest 8.4.2; pins exactly as in `requirements.txt` and as
recorded in `reports/PHASE158_RELEASE_GATES.json → verification_environment`
(httpx 0.28.1, websockets 12.0, python-dotenv 1.0.1, pandas 2.2.2, numpy 2.1.1,
pyarrow 18.0.0, pytest 8.4.2). Pins, installed versions and the recorded
environment agree, and `tests/test_dependency_pin_contract.py` enforces that
agreement. Three advisory upgrades were evaluated twice with zero new failures
and deliberately not adopted; see `reports/PHASE158_DEPENDENCY_REVIEW.md`.

## Test status (read this before judging the build)

The suite is **not green, and that is the honest state**:

* five strategy-digest tests fail deliberately (BLOCK-158-01);
* a session snapshot guard (`tests/conftest.py`) verifies every covered file
  against `BUILD_MANIFEST.sha256` at session start, restores byte-exactly any
  covered file a test rewrites, and reports `SNAPSHOT_GUARD_SUMMARY`; revision
  2's runs report the tree pristine with zero restores and no files added;
* the Git-evidence facts report `BLOCKED_EVIDENCE` (BLOCK-158-04);
* the two live-`.env` worktree-guard failures that appear when running *in a
  worktree that holds `.env`* are packaging-hygiene assertions about the
  *archive*; in the packaged tree (which contains `.env.example` only) they pass,
  which is why the extracted-package run is the one to read for packaging
  hygiene.

`reports/PHASE158_FULL_SUITE_RUN.txt` records the authoritative run against the
frozen snapshot; `PHASE158_EXTRACTED_PACKAGE_TESTS.txt` records the run against
the extracted shipped bytes. Neither is a green-suite claim.

## Status line for any downstream report

`PRODUCTION_READY: FALSE` · `FULL_TEST_SUITE: NOT GREEN / NOT COMPLETE` ·
`LIVE_ORDER_PLACEMENT: NOT PERFORMED` · `EDGE: NOT ESTABLISHED` ·
`PACKAGE CLASS: restricted evidence (not for distribution)`
