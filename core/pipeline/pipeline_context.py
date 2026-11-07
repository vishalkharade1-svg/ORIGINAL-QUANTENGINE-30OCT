"""
====================================================

Institutional Pipeline Context

Canonical Shared Pipeline State

====================================================
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from core.market_state import MarketState
from core.risk.account_state import AccountState


def _new_order_registry():
    from core.execution.order_registry import OrderRegistry
    return OrderRegistry()


def _new_economic_registry():
    from core.setup.economic_setup_registry import (
        EconomicSetupRegistry,
    )
    return EconomicSetupRegistry()


def _new_entry_tracker():
    from core.setup.entry_tracker import EntryTracker
    return EntryTracker()


def _new_zone_eligibility():
    from core.setup.zone_eligibility import ZoneEligibilityLog
    return ZoneEligibilityLog()


def _new_entry_shadow():
    from core.setup.entry_shadow import EntryShadow
    return EntryShadow()


def _new_causal_validator():
    from core.setup.causal_validation import CausalValidator
    return CausalValidator()


@dataclass(slots=True)
class PipelineContext:

    # ==========================================================
    # Persistent Session State
    # ==========================================================

    market: MarketState = field(default_factory=MarketState)

    account: AccountState = field(default_factory=AccountState)

    # The persistent OrderRegistry -- the cross-cycle source of
    # truth for the Phase 4C invariant "one setup == one primary
    # order == one trade". Session state: created once per run,
    # NEVER cleared by reset_cycle(), re-created only on a full
    # reset() so a fresh run starts empty.
    order_registry: Any = field(default_factory=_new_order_registry)

    # The persistent EconomicSetupRegistry -- the cross-cycle
    # source of truth for the Phase 4E "one trade IDEA == at most
    # one pending order" rule. It collapses economically duplicate
    # setups (identical tick-normalized fingerprints) and clusters
    # near-identical execution zones so MAX_PENDING_ORDERS is spent
    # on independent opportunities, never variants of one idea.
    # Session state exactly like order_registry: created once per
    # run, NEVER cleared by reset_cycle(), re-created only on a
    # full reset() so a fresh run starts empty.
    economic_registry: Any = field(default_factory=_new_economic_registry)

    # The persistent EntryTracker (Phase 4F STEP 3) -- post-creation
    # retracement / continuation measurement for every accepted
    # setup. Diagnostic ONLY: it measures what price did AFTER a
    # setup was discovered and feeds the feasibility report; it is
    # never consulted by any engine for accept/avoid/order/fill
    # decisions. Session state exactly like the registries: created
    # once per run, NEVER cleared by reset_cycle(), re-created only
    # on a full reset().
    entry_tracker: Any = field(default_factory=_new_entry_tracker)

    # The persistent ZoneEligibilityLog (Phase 4G STEP 12) --
    # an at-creation ledger of every canonical structural zone the
    # builder generated a candidate for, eligible or rejected, with
    # the explicit reason. Feeds the ENTRY ELIGIBILITY + ORDER
    # BLOCK FRESHNESS reports. Diagnostic ONLY, exactly like the
    # tracker: it is never consulted by any engine for accept/
    # avoid/order/fill decisions. Same session lifecycle.
    zone_eligibility: Any = field(default_factory=_new_zone_eligibility)

    # The persistent EntryShadow (Phase 4G extension) -- the three-model entry
    # reachability comparison (LIMIT_RETEST / MARKET_CONFIRMATION /
    # BREAKOUT_CONTINUATION) plus the ATR-distance-vs-expiry
    # relationship, measured on every trade-eligible structural setup.
    # Diagnostic ONLY, exactly like the tracker and the eligibility
    # log: never consulted by any engine for accept/avoid/order/fill
    # decisions, and self-gated on ENABLE_ENTRY_SHADOW. Same session
    # lifecycle.
    entry_shadow: Any = field(default_factory=_new_entry_shadow)

    # The persistent CausalValidator (Phase 4H) -- BREAKOUT_CONTINUATION
    # re-run under strict causal rules (frozen setup, trigger at the
    # trigger candle's close, entry at the OPEN of the trigger + 1,
    # deterministic intrabar SL/TP policies, R-based performance
    # metrics) plus a MARKET_CONFIRMATION rejection-stage diagnosis.
    # Diagnostic ONLY, exactly like the shadow: never consulted by any
    # engine for accept/avoid/order/fill decisions, produces no order,
    # and self-gates on ENABLE_CAUSAL_VALIDATION. Same session
    # lifecycle.
    causal_validation: Any = field(default_factory=_new_causal_validator)

    max_candles: int = 1000

    candles: deque = field(init=False)

    latest_candle: Any = None

    # ==========================================================
    # Shared Services
    # ==========================================================

    indicators: Any = None

    signal_cache: dict = field(default_factory=dict)

    # ==========================================================
    # Pipeline Outputs
    # ==========================================================

    swings: Any = None

    trend: Any = None

    # Distinct from `trend` -- see
    # core.market_structure.swing_trend_engine for why this is
    # a separate field rather than sharing `trend`.
    swing_trend: Any = None

    structure_events: Any = None

    market_structure: Any = None

    bos: Any = None

    choch: Any = None

    liquidity: Any = None

    liquidity_target: Any = None

    # Written by core.liquidity.liquidity_sweep_engine
    # (LiquiditySweepEngine). Declared here because
    # PipelineContext is slots=True -- an undeclared write
    # would otherwise raise AttributeError at runtime.
    liquidity_sweeps: Any = None

    displacement: Any = None

    fvgs: Any = None

    order_blocks: Any = None

    mitigations: Any = None

    breakers: Any = None

    cumulative_delta: Any = None

    price_ladder: Any = None

    footprint: Any = None

    volume_profile: Any = None

    confluence: Any = None

    regime: Any = None

    institutional_score: float = 0.0

    trade_setups: Any = None

    decision: Any = None

    order: Any = None

# The best-scoring accepted trade setup selected by
    # ExecutionEngine, distinct from `order` (which is reserved
    # for a future Order Intent / risk-validated object per the
    # Signal -> Risk -> Order Intent -> Execution Adapter flow).
    # backtesting/backtester.py already reads this via
    # getattr(context, "execution_signal", None).
    execution_signal: Any = None

    # Phase 4D STEP 8: the ranked batch of accepted setups
    # ExecutionEngine emitted this candle (top MAX_PENDING_ORDERS
    # by score, un-ordered setups only, pending-cap aware).
    # `execution_signal` remains the first/best for legacy
    # consumers; RiskEngine order-mints one order per entry.
    execution_signals: Any = None

    # Phase 4D STEP 8: the risk-validated orders created this
    # candle (one per accepted signal that cleared the registry
    # duplicate guard, the pending slot cap and the exposure
    # ceiling). `order` remains the first for legacy consumers.
    orders: Any = None

    position: Any = None

    # ==========================================================
    # Runtime
    # ==========================================================

    replay_index: int = 0

    completed: bool = False

    # ==========================================================

    def __post_init__(self):

        self.candles = deque(maxlen=self.max_candles)

    # ==========================================================
    # Candle Management
    # ==========================================================

    def add_candle(self, candle):

        self.latest_candle = candle

        self.candles.append(candle)

        self.replay_index += 1

    def push_candle(self, candle):

        self.add_candle(candle)

    # ==========================================================
    # Helpers
    # ==========================================================

    def last(self, offset=0):

        if len(self.candles) <= offset:
            return None

        return list(self.candles)[-(offset + 1)]

    def window(self, size):

        if size <= 0:
            return []

        return list(self.candles)[-size:]

    # ==========================================================
    # Signal Cache
    # ==========================================================

    def set_signal(self, name, value):

        self.signal_cache[name] = value

    def get_signal(self, name, default=None):

        return self.signal_cache.get(name, default)

    def clear_signals(self):

        self.signal_cache.clear()

    # ==========================================================
    # Runtime Properties
    # ==========================================================

    @property
    def candle_count(self):

        return len(self.candles)

    @property
    def current_index(self):

        return self.replay_index

    # ==========================================================
    # Per Candle Reset
    # ==========================================================

    def reset_cycle(self):

        self.clear_signals()

        # The execution signal is per-candle. Failing to clear
        # it here left the last accepted setup alive forever,
        # so the backtester re-entered the same stale trade
        # every time a position closed with no newer signal.
        self.execution_signal = None

        # The ranked selection batch and the risk-validated order
        # set are per-candle too (Phase 4D STEP 8).
        self.execution_signals = None

        self.orders = None

        # The risk-validated order is per-candle too. RiskEngine
        # rewrites it every cycle the moment a signal passes the
        # risk gates; clearing it here guarantees a stale order
        # can never be filled twice.
        self.order = None

        self.liquidity_sweeps = None

        self.swings = None

        self.trend = None

        self.structure_events = None

        self.market_structure = None

        self.bos = None

        self.choch = None

        self.liquidity = None

        self.liquidity_target = None

        self.displacement = None

        self.fvgs = None

        self.order_blocks = None

        self.mitigations = None

        self.breakers = None

        self.cumulative_delta = None

        self.price_ladder = None

        self.footprint = None

        self.volume_profile = None

        self.confluence = None

        self.regime = None

        self.institutional_score = 0.0

        self.trade_setups = None

        self.decision = None

        self.completed = False

    # ==========================================================
    # Full Reset
    # ==========================================================

    def reset(self):

        self.candles.clear()

        self.latest_candle = None

        self.indicators = None

        self.order = None

        self.position = None

        self.execution_signal = None

        self.execution_signals = None

        self.orders = None

        # A fresh run starts a fresh order registry and a fresh
        # economic registry (the whole setup -> order -> trade
        # identity space is per-run).
        self.order_registry = _new_order_registry()

        self.economic_registry = _new_economic_registry()

        self.entry_tracker = _new_entry_tracker()

        self.zone_eligibility = _new_zone_eligibility()

        self.entry_shadow = _new_entry_shadow()

        self.causal_validation = _new_causal_validator()

        self.replay_index = 0

        self.reset_cycle()