# httpx pin drift resolved (2026-10-16)

## What was wrong

`requirements.txt` declared `httpx==0.27.2`. Every environment that produced
evidence ran **0.28.1**. The drift was first recorded in Phase132 and carried,
unresolved, through every phase since — noted in at least eight reports and
never acted on, because pin changes were deferred to a green-run maintenance
window that cannot arrive.

## Why it was not cosmetic

Phase134 found the consequence during a real order experiment
(`reports/PHASE134_ORDER_EXPERIMENT.md`):

> Cancel initially UNCONFIRMED (open count 1, position flat). Root cause:
> `DeltaSignedREST.delete` used `client.delete(..., content=...)`, removed in
> installed httpx 0.28.1 (pinned 0.27.2) → client-side TypeError swallowed →
> cancel never sent. Real trading-safety defect, not a test pin.

A cancel that is never sent, with the error swallowed before it reaches the
caller, is about as bad as a defect gets in an execution path. It existed
*because* the environment was ahead of the pin.

The repair (then) made the code version-agnostic rather than pinning reality
down: `core/exchanges/delta/delta_auth.py` now prefers `request("DELETE", …)`
and falls back to the `delete()` shortcut, with byte-identical signed bodies on
both branches, covered by `tests/test_delta_delete_signing_phase154.py`.

## Why the pin was the thing that was wrong

The evidence is unambiguous about which version the work was done on:

- Every capture and every full-suite run since Phase132 ran under 0.28.1.
- The Phase134 trading-safety defect was **found** under 0.28.1, and its fix
  **verified** under 0.28.1.
- The pin at 0.27.2 described a version nothing was running.
- Nothing depended on the old value: no test hardcoded it, and the compat test
  is deliberately version-agnostic — its docstring reads "DeltaSignedREST.delete
  works on httpx 0.27 and 0.28".
- `pip-audit` reports no advisory against 0.28.1, so this is not an
  advisory-driven change.

The alternative — downgrade the environment to 0.27.2 to match the pin — was
rejected: it would invalidate the environment of record for all recent evidence
and force a full re-baseline, in exchange for an older version with no
demonstrated benefit.

## What changed

1. `requirements.txt`: `httpx==0.27.2` → **`httpx==0.28.1`**, with the reason
   recorded in the file itself.
2. `reports/PHASE157_RELEASE_GATES.json`: the `verification_environment` block
   now names the **full dependency set** the evidence was produced under, not
   just the interpreter and runner.
3. `tests/test_dependency_pin_contract.py` (new, 4 tests): the declared pins and
   the recorded evidence environment must name exactly the same packages and
   versions, and the record must state its interpreter, runner and platform. It
   reads the highest-numbered gates file, so it advances with the release
   instead of needing re-pointing. **Drift now fails a test instead of sitting
   in a report.**

## What this does not claim

It does not claim a fresh full-suite run under the new pin set. It does not need
to: the new pin set **is** the environment the last authoritative full-suite run
executed under (`reports/PHASE155_FULL_SUITE_RUN2.txt` — 46F/3944P/10S/0E, on
the pre-Phase156 tree). The tree has advanced since; the current tree's focused
suites (76 tests) were run under exactly these versions, and the dependency
evaluation covered the suite under these versions plus three advisory upgrades.

The pyarrow/python-dotenv/pytest advisories remain **evaluated but not adopted**
(`reports/DEPENDENCY_UPGRADE_EVALUATION.md`) — a separate decision, deliberately
not bundled into this one.

## Operator veto

This is a contract change, not a bug fix, and it is reversible in one line: set
`httpx==0.27.2` in `requirements.txt` and re-record the environment map. Doing so
re-creates the drift deliberately, which is a legitimate choice — but it should
be a choice, stated, rather than an accident nobody noticed.
