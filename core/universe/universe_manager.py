"""
====================================================

QuantEngine

Universe Manager

Phase 6B -- Market Universe.

Builds the ELIGIBLE market universe from the persistent
instrument registry through the full gate cascade:

    registry (discovered, confirmed)            -- source of truth
    policy  (UniversePolicy)                    -- thresholds
    liquidity_provider / history_provider       -- data (injectable)

Half the safety is here:

  - a NEWLY_LISTED single-sighting candidate is NEVER
    eligible on the same pass it was discovered (it needs a
    later-pass confirmation -> ACTIVE first, per 6A) ;
  - a DELISTED instrument can never re-enter the universe ;
  - every re-check writes ELIGIBILITY state back to the
    registry (ELIGIBLE / INELIGIBLE + reason), so the
    persistent catalog always reflects the last verdict ;
  - with no provider, or no data, the universe degrades to
    EMPTY -- never a silent everything-goes catalog.

Providers are duck-typed and mockable:

    provider.quote_volume_24h(symbol) -> float | None
    provider.history_bars(symbol, timeframe) -> int | None
====================================================
"""

import time

from core.registry.eligibility import (
    IneligibleReason,
    InstrumentEligibility,
)
from core.registry.instrument_registry import (
    InstrumentRegistry,
)
from core.registry.product_types import (
    PRODUCT_STATE_NEWLY_LISTED,
)
from core.universe.market_universe import MarketUniverse
from core.universe.universe_policy import UniversePolicy


class UniverseManager:

    def __init__(
        self,
        registry=None,
        policy=None,
        liquidity_provider=None,
        history_provider=None,
        evaluator=None,
        clock=None,
    ):
        # NOTE: `registry if registry is not None` -- an EMPTY
        # InstrumentRegistry is falsy (it defines __len__), so
        # `registry or InstrumentRegistry()` would silently replace it.
        self.registry = (
            registry if registry is not None else InstrumentRegistry()
        )
        self.policy = policy or UniversePolicy()
        self.liquidity_provider = liquidity_provider
        self.history_provider = history_provider
        self.evaluator = evaluator or InstrumentEligibility(
            min_quote_volume_24h=self.policy.min_quote_volume_24h,
            min_history_bars=self.policy.min_history_bars,
        )
        self._clock = clock or time.time

    # =====================================================
    # Eligibility cascade
    # =====================================================

    def build_universe(self, timeframe="1m"):
        """Run the gate cascade over every confirmed instrument and
        write ELIGIBLE / INELIGIBLE back to the registry.
        Returns the MarketUniverse snapshot (the ELIGIBLE cut)."""
        eligible = []
        reasons = {}

        for instrument in self.registry.discoverable():
            # Confirmation gate (6A): a first-sighting candidate
            # cannot be traded until a later pass makes it ACTIVE.
            if instrument.state == PRODUCT_STATE_NEWLY_LISTED:
                reasons[instrument.symbol] = IneligibleReason.NOT_CONFIRMED
                continue

            volume = (
                self.liquidity_provider.quote_volume_24h(
                    instrument.symbol
                )
                if self.liquidity_provider is not None
                else None
            )
            bars = (
                self.history_provider.history_bars(
                    instrument.symbol, timeframe
                )
                if self.history_provider is not None
                else None
            )

            ok, reason = self.evaluator.evaluate(
                instrument,
                quote_volume_24h=volume,
                history_bars=bars,
            )
            reasons[instrument.symbol] = reason or "ELIGIBLE"
            if ok:
                self.registry.mark_eligible(instrument.key)
                eligible.append(instrument)
            else:
                self.registry.mark_ineligible(
                    instrument.key, reason
                )

        return MarketUniverse(
            policy=self.policy,
            instruments=eligible,
            timeframe=timeframe,
            captured_at=self._clock(),
            reasons=reasons,
        )

    # =====================================================
    # Refresh (discovery + eligibility)
    # =====================================================

    def refresh(
        self,
        client=None,
        normalizer=None,
        run_discovery=True,
        timeframe="1m",
    ):
        """Full heartbeat: product discovery refresh (optional)
        then the eligibility cascade. Returns the universe."""
        if run_discovery:
            self.refresh_discovery(client=client,
                                   normalizer=normalizer)
        return self.build_universe(timeframe=timeframe)

    def refresh_discovery(self, client=None, normalizer=None):
        """Only the product-catalog refresh -> registry mutation.
        A newly listed product lands in the registry as a
        NEWLY_LISTED candidate; it is NOT tradable until later
        passes confirm it and this manager marks it eligible."""
        from data.delta.product_discovery import (
            refresh_instrument_registry,
        )
        return refresh_instrument_registry(
            self.registry,
            client=client,
            normalizer=normalizer,
        )

    # =====================================================
    # Convenience queries
    # =====================================================

    def executable_symbols(self):
        """The ELIGIBLE cut as symbols from the registry itself;
        the canonical input for Phase 6C multi-symbol scanning."""
        return [i.symbol for i in self.registry.executable()]

    def executable_instruments(self):
        return list(self.registry.executable())