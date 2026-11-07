# Independent Audit Prompt — QuantEngine Phase 158 release-repair candidate

You are an independent adversarial auditor. Everything you need is in the
provided archive `QuantEngine_PHASE158_RELEASE_CANDIDATE.zip` and the two
companion deliverables that travel beside it:

* `RELEASE_HASH_PHASE158.txt` — the detached hash record (the archive's own
  SHA-256, member count and byte count). It is deliberately **outside** the ZIP:
  an archive cannot truthfully embed a hash of itself.
* `PHASE158_SELF_AUDIT.md` (+ `PHASE158_EXTRACTED_PACKAGE_TESTS.txt`) — the
  self-audit against the final archive bytes and the extracted-package test
  log. They describe the shipped bytes, so they cannot live inside them. (The
  archive does carry `reports/PHASE158_SNAPSHOT_AUDIT.md`, which audits the
  frozen snapshot that was packed; read it as the snapshot's audit, not as an
  audit of the archive bytes.)

This revision responds to an independent audit of the first Phase158 build.
The findings and their dispositions are recorded in
`reports/PHASE158_AUDIT_REPAIRS.json` (the post-build bundle carries
`PHASE158_AUDIT_DISPOSITION.json` with the audited revision's identity).
Verify those repairs like every other claim, and report any disposition you
cannot reproduce.

Hand the reviewer the ZIP **together with** its companions. Auditing the ZIP
alone makes items 1, 13 and 16 impossible to complete, which is a limitation
of the handoff, not of the archive.

Do not trust `NEXT_ACTIONS.md`, `IMPLEMENTATION_STATE.md`, `reports/PHASE158_*`
or any claim below without reproducing it. Fix nothing; report only.

Work from a **fresh extraction** of the ZIP into a clean directory. The archive
contains no `.git` directory anywhere: Git-ancestry claims are therefore
unverifiable from the archive alone and must be labelled `UNVERIFIABLE`-class
(see item 6), never PASS.

## The 16 independent-verification items

1. **Archive identity, and non-circularity.**
   Recompute the SHA-256 of the ZIP. It must equal the value in
   `RELEASE_HASH_PHASE158.txt`, and the member/byte counts must agree too.
   Then confirm the converse: no file inside the ZIP contains that SHA-256
   (search the extracted tree for the literal). Report any embedding as HIGH.

2. **Manifest completeness and determinism.**
   Run `python scripts/generate_manifest.py --root . > /tmp/regen` and compare
   **bytes** against the shipped `BUILD_MANIFEST.sha256`: byte-for-byte or
   FAIL. The manifest is LF-only (no `\r` bytes) and the script writes UTF-8
   bytes to stdout, so the reproduction is byte-exact on any platform; the
   revision-1 audit found the shipped form was CRLF, which a platform using LF
   conventions could not reproduce byte-for-byte (F-03, repaired in revision
   2). Then
   `--verify` (expect `MANIFEST_PASS (0 problems)`). Independently check that
   every regular file in the tree is covered exactly once, that the manifest
   does not list itself, and that only the documented exclusions are absent.
   Prove the verifier can fail: corrupt one byte, add one file, delete one file,
   duplicate one line, and add one malformed line — each must be reported.

3. **The LF-restoration repair.**
   `research/phase11f/freeze_manifest.json` pins ten inputs by raw-byte SHA-256.
   Recompute each: all ten must match. Ten files plus five canonical-JSON
   artifacts (`research/results/phase14_*`, `phase15_*`, `phase17_*`,
   `phase18_*`, `phase19_*`) were LF-restored in Phase 158; verify no file in
   those sets contains CRLF. Then prove the repair preserved *content*: compare
   each against the same member in a pre-Phase158 archive (e.g.
   `QuantEngine_PHASE157_RELEASE_CANDIDATE.zip`, if you hold it) and confirm the
   only difference is line endings. `research_log.json` is the documented
   11F-4 exception whose pin is stale for an unrelated, authorised reason —
   check that it is labelled as such rather than silently re-pinned.

4. **The reconstructed dataset.**
   `data/history/BTCUSDT_1m_phase19_extension.json` did not ship in any archive
   from Phase131 to Phase157 because it is gitignored by this project's own
   packaging contract; ten tests failed for that reason alone. Reconstruct the
   claim: (a) its rows, canonicalised as sorted-key compact JSON, must hash to
   `extended_span.dataset_hash` in `research/results/phase19_oos_data_extension.json`
   (`4feccebb3c546de365927b16668195fe871c0cca088b7b1cef8c0bf755aaaab1`);
   (b) the row set must be exactly the first `prior_received` (11899) rows of
   `data/history/BTCUSDT_1m_oos_topup.json` **when its rows are ordered
   ascending by time** — the stored topup array is not itself time-sorted, and
   the artifact's disclosure now says so (the audit's F-10); (c) every bar must be strictly
   after the recorded Gate-A boundary; (d) the file must carry its
   `reconstruction` disclosure. If any of those fails, the reconstruction is
   wrong, not the test.

5. **Strategy-digest changes were NOT re-pinned.**
   Five tests pin a strategy digest `c52e648c…`. It matches no revision
   recoverable from any archive on disk. Confirm those five tests are still
   present, still assert the old digest, and still FAIL — deliberately. Confirm
   `scripts/recertify_strategy_digest.py` still returns `STATUS: BLOCKED` and
   that nothing rewrote or auto-updated the pin. A Phase158 build that made
   these green by updating the expected value would be WORSE than one that
   leaves them red. Report any re-pin as CRITICAL.

6. **Git-evidence honesty (the 40 gated facts).**
   The tree carries no `.git`. In Phase157, 19 Git-ancestry tests failed and 21
   more *passed vacuously* (a failed `git` command returns empty output, and
   empty output satisfied `assertEqual(out, "")` / `assertEqual(hits, [])`).
   Phase158 installed `tests/evidence_mode.py` and gated all 40 facts as
   `BLOCKED_EVIDENCE` (`reports/PHASE158_GIT_EVIDENCE_STATUS.json`).
   Verify: (a) every one of the 40 is reported as blocked/skipped-with-reason
   and none is reported as passed; (b) two of them matter especially —
   `test_stage123_operational.py::test_security_scan_no_real_credentials` and
   `test_stage4_paper_certification.py::test_research_byte_unchanged`; (c) the
   guard steps aside correctly in a real repository — create a throwaway temp
   repo, commit a file, and show the same guard functions PASS there. A guard
   that blocks in a repo too is a suppression, not a contract.

7. **Stale evidence is labelled, not deleted.**
   `reports/PHASE157_SELF_AUDIT.md` (sha256
   `b83553cb914ab26e58492fab8cf291beefc9859335eb886edaa421ac598774a4`) describes
   a *superseded* 1,817-member build (`72fe28e0…`), not the 1,820-member build
   Phase157 shipped. Verify its bytes are unchanged and that
   `reports/PHASE158_PROVENANCE.json` labels it as historical and states which
   build it describes. Verify `reports/RELEASE_PROVENANCE_PHASE132.json` is the
   Phase132 record renamed (sha256
   `05df5fa91b4c0350aedf905f09eb3cdbc96d15abdfbed2876fbfa825f36e985e`, bytes
   unchanged) and that the ambiguous generic name is gone. Any record that
   names a superseded build as the current one is HIGH.

8. **Secrets: packaged tree and final archive.**
   Run `python scripts/security/scan_secrets.py` over the extracted tree: expect
   no non-empty credential assignment. Confirm the scanner actually looks at
   `.env`/Testnet/Sandbox names and that its rules are the ones it claims
   (read the rule table; do not accept the summary). Confirm no `.env`, `.pem`,
   `.key`, `.secret`, `.pyc` or cache directory is present in the ZIP.
   Independently grep the raw ZIP bytes for `DELTA_`, `api-key`, `Bearer ` and
   any 64-hex-then-credential-shaped pair.

9. **Privacy: who is in this package, and is that deliberate?**
   This archive is a **restricted evidence package**, not a distributable: it
   deliberately ships raw private captures that carry the operator's account
   identifier and venue order ids. (This prompt does not repeat the identifier
   value: `scripts/security/scan_privacy.py` parameterises rule A with it, and
   rule A requires it to appear nowhere but those captures. Read the value from
   the scanner, not from here.) Verify the confinement claim mechanically:
   `python scripts/security/scan_privacy.py --root .` must report
   `PRIVACY_SCAN_PASS`, the set of files containing the account identifier must
   equal exactly the six enumerated allowlisted paths in
   `reports/PHASE158_PRIVACY_REVIEW.md`, and no raw order id may appear in
   `reports/`, `docs/` or `research/results/` **except in files that are
   byte-identical to their input-archive member** (the enumerated sealed
   historical baseline; any new or modified carrier must fail). The scan's
   verdict is scoped by its own `publication_clearance: NOT_CLEARED` field:
   `PRIVACY_SCAN_PASS` is a restricted-package verdict and never a publication
   clearance (the revision-1 audit read it as one — F-01). Then attack it: create a copy of
   the tree, plant the identifier in one extra file, and confirm the scanner
   fails. Verify the six allowlisted captures are covered by the manifest.
   Confirm the review does NOT claim the package is safe to publish.

10. **Dependency pins, environment, and advisories.**
    `requirements.txt` must name exactly the versions in
    `reports/PHASE158_RELEASE_GATES.json → verification_environment.dependencies`,
    with no drift (enforced by `tests/test_dependency_pin_contract.py`; run it).
    Compare against the interpreter/pytest actually present in your environment
    and against the recorded platform. For each of the three advisory upgrades
    (python-dotenv 1.2.2, pyarrow 23.0.1, pytest 9.0.3) check
    `reports/PHASE158_DEPENDENCY_REVIEW.md` states a decision and a reason;
    confirm no pin was changed without evidence, and confirm whether the
    remaining advisories touch the pinned versions at all.

11. **Trading safety was not weakened.**
    From source only: (a) no live-order path can run without an explicit
    `--execute` (check `scripts/bounded_testnet_order_experiment.py`,
    `scripts/funding_settlement_hold.py`); (b) endpoints are India **Testnet**
    and a mismatch is refused *before* any credential use; (c) signing is the
    canonical `method+timestamp+path_with_query+body` HMAC-SHA256 and the
    signed body is the body sent; (d) a cancel whose re-query cannot confirm a
    terminal state is reported as unconfirmed, never as success; (e) the
    windowed fill reconciler refuses an undeclared timestamp unit and cannot be
    confused with account-level `MATCHED`. Quote `file:line` for each.

12. **The authoritative full suite.**
    Re-run `python -m pytest -q -p no:cacheprovider --tb=short` from the
    extracted tree. Compare the failure *multiset* (not just the count) against
    the dispositions in `reports/PHASE158_FULL_SUITE_RUN.txt` and
    `reports/PHASE158_BLOCKERS.json`. Expected here: the five strategy-digest
    failures (deliberate change detectors) and the Git-evidence gates. Any
    failure outside the declared disposition set is a finding; so is any
    declared failure that no longer fails.
    The suite also runs a session snapshot guard (`tests/conftest.py`): it
    verifies every covered file against the manifest at session start,
    restores a known-rebuilt watchlist byte-exactly after every test, sweeps
    the whole covered set every 50 tests and at session end, and ends with a
    machine-readable `SNAPSHOT_GUARD_SUMMARY {json}` line. After the run,
    re-run `python scripts/generate_manifest.py --root . --verify`: it must
    still print `MANIFEST_PASS (0 problems)`. (F-02's failure mode was a run
    that left a covered file rewritten; the guard is the repair, and the
    summary records any in-run rewrite it neutralised — non-empty on platforms
    whose newline conventions differ from the recorded bytes, empty on the
    build platform.)

13. **Extraction equals packaging.**
    Extract again into a fresh directory and compare every member hash against
    `BUILD_MANIFEST.sha256` (expect 0 mismatch, 0 missing, 0 extra). Then run
    the release-consistency tests against the extracted package:
    `tests/test_release_consistency_phase155.py`,
    `tests/test_release_records_phase158.py`, `tests/test_phase158_*`. Confirm
    the detached record is *not* inside the tree and that the extracted tree
    verifies clean — and still verifies clean *after* the full suite of item 12
    (the snapshot guard makes that invariant portable across platforms).

14. **No economic claim outran the evidence.**
    Confirm every edge/economics artifact still states `EDGE NOT ESTABLISHED`
    where it did before, that no repaired test was changed from an economic
    assertion into a PIN assertion, and that no missing economic component was
    zero-filled to make a test pass. Cite any violation with `file:line`.

15. **Blocker list is complete and still honest.**
    `reports/PHASE158_BLOCKERS.json` must still list: the operator-side IP
    whitelist blocking funding-through-settlement and repeat-match evidence
    (`157.33.197.21`), the strategy-digest re-certification requiring the
    original Git checkout and research re-execution, the 40 Git-evidence facts,
    the five deliberate failures, the independent-audit dependency (this
    task), and the non-canonical-platform limitation on the sealed research
    builders (`reports/PHASE158_AUDIT_REPAIRS.json`). Check nothing was downgraded from BLOCKED to PASS by wording.

16. **Adversarial sweep: find the load-bearing lie.**
    Treat the entire deliverable as a claim to falsify. Look specifically for:
    a record describing bytes other than the shipped ones; a test that cannot
    fail (empty-output, tautology, or silently-skipped assertion); an assertion
    weakened relative to Phase157; a digest updated to match new bytes; a count
    in a report that differs from what the evidence shows; and any claim of
    `PRODUCTION_READY`, `EDGE ESTABLISHED`, or "all tests green" anywhere.
    Report what you find with reproduction steps, ordered by severity.

## Rules

- Distinguish static review from executed tests. Cite `file:line` for every
  claim, and give the exact command for every execution.
- Allowed statuses: IMPLEMENTED / EXECUTED / TESTED / VERIFIED /
  BLOCKED_EVIDENCE / NOT_PRODUCTION_READY. Never PASS a claim you did not
  reproduce.
- Historical digests that cannot be reproduced from the archive alone
  (`c52e648c…`, `99a47bdd…`, `9eff61b7…`) are `UNVERIFIABLE`, never PASS.
- The absence of `.git` means no ancestry claim can be verified here; item 6 is
  about whether the *tree states that honestly*, not about proving ancestry.
- Severity: CRITICAL / HIGH / MEDIUM / LOW. Fix nothing; report only.

## Deliverable

A machine-readable findings JSON plus a concise verdict. `PRODUCTION_READY`
only if every mandatory gate passes with reproduced evidence; otherwise
`NOT_PRODUCTION_READY` with the blocker list. State explicitly which of the 16
items you could not complete and why.
