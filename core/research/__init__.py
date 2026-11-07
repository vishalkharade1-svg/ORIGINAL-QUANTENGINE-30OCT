"""
====================================================

QuantEngine

RESEARCH namespace (Phase 7+)

CIENTIFICALLY isolated from the frozen production path
(PHASE 1-6E). Modules under core.research.* are NEVER
imported by any engine, the Backtester, the BrokerEngine, or
the runtime -- they exist to run offline experiments and
produce EVIDENCE, never to change strategy or execution.

Phase 7 (breakout asymmetry) lives here so the bullish-vs-
bearish BREAKOUT investigation can proceed with the entire
production pipeline frozen, exactly as the research protocol
requires:

    research -> hypothesis -> isolated research path ->
    unit tests -> out-of-sample validation ->
    comparison vs frozen baseline -> production integration

Nothing in core.research may call a frozen production module
for a decision; it may only RE-READ frozen records captured
by production (e.g. the CausalValidator's CausalValidationState
dataset) and factor them into distributions.
====================================================
"""
