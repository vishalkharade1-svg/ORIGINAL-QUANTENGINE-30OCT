# QuantEngine — LEVEL 4 Engineering Report

## Baseline

LEVEL 3 checkpoint:
- HEAD: `ffefa14a8729f6d2160db3735a06257cbb6ab48b`
- Real hypotheses: 0
- OOS readiness: BLOCKED / WAITING_FOR_DATA
- Production readiness: FALSE

## Level 4 change

Runtime trading policy is now separate from frozen research/OOS thresholds.
The default trading bounds are inclusive:
- minimum: 1.0R (1:1)
- maximum: 20.0R (1:20)
- below the configured minimum: rejected
- above the configured maximum: rejected

The frozen Level-3 research/OOS identity remains unchanged:
- `config.risk_settings.MIN_RISK_REWARD = 6.0`

The runtime authority is `core.risk.trading_policy`: it provides a global
policy plus exact-instrument overrides. Overrides are keyed by the actual
traded symbol/instrument identifier, persist as deterministic JSON runtime
state, and are exposed through authenticated `/risk-policy` API routes and
the browser dashboard.

## Trailing stop + exit management

Trailing management is enabled by default for runtime trading policy. A
normal 1:1..1:20 target remains the economic target boundary, while the
trade may be protected by a trailing stop before that target is reached.
Default trailing parameters are 1.0R activation and 0.5R distance and are
operator-changeable globally or per instrument from the frontend.

A position can therefore terminate by:
- initial protective stop;
- trailing stop;
- reaching the configured target;
- an explicit QuantEngine exit/book-profit signal at the observed market price;
- an opposite-direction signal when the instrument policy enables automatic
  opposite-signal exit.

Trailing movement remains causal: a trail derived from a completed candle
becomes active on the next candle. Stops never loosen. Live exchange trailing
execution remains fail-closed until the venue execution contract is verified.

## Safety

- `is_production_ready` remains `False`.
- No live order was submitted.
- No sandbox order was submitted.
- No production credentials were used.
- No production strategy promotion was performed.
- Level-3 OOS protocol was not executed or altered.
- Old Level-3 strategy-hash pins are intentionally not re-registered: Level 4 changes runtime strategy files and therefore require a future explicit Level-4 research/preregistration cycle before OOS claims can be made.

## Tests

Focused Level-4 and affected runtime tests: PASS.

Latest focused run:
- 44 tests: OK
- `python -m compileall -q .`: clean

Additional earlier Level-4 suite:
- 15 Level-4 / boundary tests: OK

The full repository suite was not certified green in this session. The existing repository contains historical forensic pins and the Level-4 strategy-file changes intentionally invalidate the old frozen strategy hash. No old hash was silently re-registered.

## Status

LEVEL 4 ENGINEERING: implemented for the R:R/exit-policy scope.
LEVEL 3 OOS CERTIFICATION: preserved/frozen but not re-certified after Level-4 changes.
PAPER TRADING: not authorized by this change.
PRODUCTION READY: FALSE.
