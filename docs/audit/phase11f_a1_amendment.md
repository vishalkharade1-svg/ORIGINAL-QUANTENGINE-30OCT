# A1 Amendment — Candidate Cross-Bar State Preservation

Companion note to `research/phase11f/11f5_a1_amendment.json` (machine record).

## Bug

`_Base.prepare()` discarded `self._feat` on every rebuild. The harness
feeds a growing prefix, so every bar triggered a rebuild and wiped
`pend` / `last_high` / `last_low`. Stateful hypotheses armed setups
they could never trigger.

## Reproduction (pre-fix, on identical bars)

* Direct: `BreakerRetest` stepped sequentially over the fixed BTCUSDT
  fold-0 slice → **2 signals**.
* Harness: same slice through `H.run_candidate()` → **0 signals,
  0 orders**.

## Fix (+17/−0 lines, `_Base.prepare` only)

Retain the three state keys across rebuilds when dataset identity
(first-bar time) and config match and length is non-shrinking —
i.e. exactly the harness's growing-prefix pattern. Fresh datasets or
configs still reset fully.

## What did NOT change

Hypothesis definitions, frozen parameters, thresholds, indicators, RR,
stops, targets, entry/exit models, costs, sizing, leverage, caps,
symbols, timeframes, datasets, seeds, regime/MC/RB configuration.
`features.py`, `harness.py`, `contracts.py`, `metrics.py`,
`validation.py`, `hypotheses.json`, `datasets.json` are byte-identical
to preregistration (manifest hashes verify, modulo the ledger's
authorized result halves).

## Status honesty

Whether any economic quantity was observed before the fix cannot be
proven from git/artifacts (single-commit phase): **NOT_VERIFIABLE**.
The fix was nevertheless required for methodological validity — without
it, four of eight preregistered hypotheses were mechanically unable to
emit the signals their frozen definitions specify. A1 is a repair, not
an optimization: post-fix evidence (7× INSUFFICIENT, 1× FAIL) is, if
anything, less flattering than silence would have been.
