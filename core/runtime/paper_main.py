"""
====================================================

QuantEngine

Paper Main (Phase 9P-a)

The canonical PAPER-mode startup bridge between the CLI
entry point (main.py) and the Phase 6E RealTimeEngine
multi-symbol runtime. Before this module existed, main.py
drove only the LEGACY single-symbol PaperTradingEngine /
websocket_client path -- the multi-symbol runtime was
never reachable from the entry point. This bridge closes
that integration gap.

    build_paper_engine(...)  -> assembled RealTimeEngine
    tick(engine, ...)        -> one non-blocking poll step
    run_paper_forever(...)   -> blocking poll loop (main.py)

Design principles (inherited from the 6E orchestrator):

  * canonical runtime -- the SAME RealTimeEngine ->
    PipelineRegistry -> PaperRuntime -> BrokerEngine
    (dry_run) stack that the runtime integration tests
    exercise. No strategy / risk / execution logic is
    re-implemented here.
  * injectable by construction -- every collaborator
    (universe_manager, transport_factory, world_factory,
    clock) is a parameter, so offline tests can drive the
    exact same build path with a fake snapshot universe,
    fake transport and a scripted world. main.py uses the
    production defaults.
  * explicit-symbol universe default -- in the absence of
    live liquidity/history providers (which do not yet
    exist), the manager derives the eligible cut from
    settings.SYMBOLS (UNIVERSE="explicit"), mirroring the
    repository's existing explicit-universe precedent
    (core.market_registry builds one Market per SYMBOLS
    entry). Discovery is a no-op; the engine's
    RefreshScheduler still re-polls the shared manager on
    cadence.
  * paper-only by construction -- every runtime runs the
    BrokerEngine with dry_run=True through the
    PaperExecutionAdapter; zero exchange writes. No
    strategy is ever auto-promoted.
====================================================
"""

import logging
import os
import time

from config import risk_settings
from config.settings import settings

from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_STATE_ELIGIBLE
from core.universe.market_universe import MarketUniverse
from core.universe.universe_policy import UniversePolicy

log = logging.getLogger(__name__)


class ContractUnavailableError(RuntimeError):
    """Verified contract metadata is unavailable for a symbol.

    Raised ONLY in strict-contract mode (see
    ``ExplicitSymbolUniverseManager(strict_contracts=True)`` or
    ``QE_REQUIRE_VERIFIED_CONTRACTS``): unknown contract metadata
    fails closed instead of fabricating SPOT economics for an
    arbitrary symbol.
    """


# =====================================================
# Provider-backed universe thresholds (Phase 9P-d)
# =====================================================


def _configured_float(raw):
    """Parse an operator threshold env value.

    '' / None / whitespace -> None (unconfigured, no numeric
    bound). Any non-empty value must parse to a float else the
    config is INVALID -> raise (fail fast, never silently run
    with a wrong bound)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Invalid MIN_QUOTE_VOLUME_24H threshold: {!r}".format(raw)
        ) from error
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(
            "Invalid MIN_QUOTE_VOLUME_24H threshold: {!r}".format(raw)
        )
    return value


def _configured_int(raw):
    """Same semantics for the integer history-bar threshold."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Invalid MIN_HISTORY_BARS threshold: {!r}".format(raw)
        ) from error


def provider_policy():
    """The UniversePolicy for the provider-backed universe, built
    from the Phase 9P-d operator thresholds (settings).

    An unconfigured liquidity threshold still REQUIRES a measured
    volume (the gate denies None); a configured value adds the >=
    bound. `requires_history` is driven by whether the operator set
    MIN_HISTORY_BARS."""
    return UniversePolicy(
        min_quote_volume_24h=_configured_float(
            settings.MIN_QUOTE_VOLUME_24H
        ),
        min_history_bars=_configured_int(
            settings.MIN_HISTORY_BARS
        ),
    )


def build_provider_universe_manager(
    registry=None,
    policy=None,
    liquidity_provider=None,
    history_provider=None,
    timeframe="1m",
):
    """Assemble a canonical Phase 6B UniverseManager backed by the
    real Delta liquidity + history providers (Phase 9P-d).

    This is the provider FEEDING the existing cascade, not a
    second universe manager: the canonical UniverseManager +
    InstrumentRegistry + eligibility pipeline decides the eligible
    cut from REAL provider data. Discovery still populates the
    registry via refresh_discovery(); build_universe() runs the
    gate cascade with quote_volume_24h + history_bars from the
    providers.

    Every collaborator is injectable so offline tests exercise the
    exact same path with fake providers and zero network. When no
    providers are supplied the real Delta-backed ones are used.

    timeframe: the DEFAULT trade timeframe the manager passes to
    the history provider on every build (1m unless overridden by
    the caller's build_universe(timeframe=...)).
    """
    from core.registry.instrument_registry import InstrumentRegistry
    from core.universe.liquidity_provider import DeltaLiquidityProvider
    from core.universe.history_provider import DeltaHistoryProvider
    from core.universe.universe_manager import UniverseManager

    effective_policy = (
        policy if policy is not None else provider_policy()
    )

    provider_registry = (
        registry if registry is not None else InstrumentRegistry()
    )

    liquidity = (
        liquidity_provider
        if liquidity_provider is not None
        else DeltaLiquidityProvider()
    )
    history = (
        history_provider
        if history_provider is not None
        else DeltaHistoryProvider(
            lookback_days=settings.PROVIDER_HISTORY_LOOKBACK_DAYS,
        )
    )

    return UniverseManager(
        registry=provider_registry,
        policy=effective_policy,
        liquidity_provider=liquidity,
        history_provider=history,
    ), provider_registry, liquidity, history


# =====================================================
# Explicit-symbol universe manager (6B duck)
# =====================================================


class ExplicitSymbolUniverseManager:
    """A phase-6B-compatible universe manager whose eligible
    cut is the explicit SYMBOLS list.

    Exposes exactly the two methods the RefreshScheduler /
    RealTimeEngine consume:

        refresh_discovery(client=None, normalizer=None)
        build_universe(timeframe="1m") -> MarketUniverse

    Discovery is a deliberate no-op: the eligible cut is
    declared by configuration, not discovered (UNIVERSE=
    "explicit"). The engine still drives this manager's
    build_universe through the RefreshScheduler on cadence,
    exactly as it would a full discovery-backed manager.
    """

    def __init__(self, symbols=None, timeframe="1m",
                 strict_contracts=None):

        raw = list(symbols if symbols is not None else settings.SYMBOLS)

        # Phase-13 fail-closed contract policy (§14 Option B):
        # None (default) reads QE_REQUIRE_VERIFIED_CONTRACTS, so
        # the default path preserves the explicitly synthetic
        # fallback (labeled, never derivative-realistic) while an
        # operator can require verified contracts and fail closed
        # on unknown metadata instead of fabricating it. Provider
        # discovery (§14 Option A) remains future work.
        if strict_contracts is None:
            strict_contracts = (
                os.getenv("QE_REQUIRE_VERIFIED_CONTRACTS", "")
                or "").strip().lower() in ("1", "true", "yes", "on")
        self.strict_contracts = bool(strict_contracts)

        self.instruments = [
            _eligible_instrument(symbol,
                                 strict=self.strict_contracts)
            for symbol in raw
            if symbol and str(symbol).strip()
        ]

        self.timeframe = timeframe or settings.TIMEFRAME

        self.discovery_attempts = 0

    # -------------------------------------------------

    def refresh_discovery(self, client=None, normalizer=None):
        """Explicit universe: nothing to discover. Records the
        pass (observable) and returns the catalog size."""

        self.discovery_attempts += 1

        return {
            "explicit": True,
            "instruments": len(self.instruments),
        }

    def build_universe(self, timeframe="1m"):
        """The ELIGIBLE cut as a MarketUniverse snapshot."""
        return MarketUniverse(
            policy=UniversePolicy(),
            instruments=self.instruments,
            timeframe=timeframe or self.timeframe,
            captured_at=time.time(),
        )


def _eligible_instrument(symbol, strict=False):
    """Build an ELIGIBLE Instrument record for one explicit
    symbol. String ids keep the canonical identity stable
    (exchange, instrument_id) across restarts; precision is
    the minimal printable contract so the eligibility gates
    pass. The explicit path is the documented fallback until
    live providers exist.

    SECOND-PASS FORENSIC WARNING (2026-09-22): this fallback
    FABRICATES contract metadata — ``product_type="SPOT"`` with
    fixed tick/quantity precision is assumed, never discovered
    from the venue.  It is SYNTHETIC metadata, unsafe for
    derivatives/options sizing, and explicitly tagged as such
    via ``metadata["synthetic_fallback"]``.  The verified
    contract factory (``contract_spec_from_instrument``) refuses
    it fail-closed (no verified_* evidence fields), which is
    the intended behavior until real provider discovery lands.
    Paper simulation on this path must never be presented as
    derivative-realistic.

    Phase-13 fail-closed policy: ``strict=True`` (or the
    ``QE_REQUIRE_VERIFIED_CONTRACTS`` environment gate via
    ``ExplicitSymbolUniverseManager``) raises
    ``ContractUnavailableError`` instead of fabricating — a
    derivative symbol with unavailable venue metadata yields
    explicit UNAVAILABLE, never misleading sizing."""

    if strict:
        raise ContractUnavailableError(
            "verified contract metadata is unavailable for "
            "symbol %r; refusing to fabricate SPOT economics "
            "(explicit-universe fallback disabled by strict "
            "contract policy)" % (symbol,))

    instrument = Instrument(
        instrument_id=symbol,
        symbol=symbol,
        exchange="DELTA",
        product_type="SPOT",
        underlying_asset=symbol,
        quote_asset="USDT",
        tick_size=0.01,
        quantity_step=0.001,
        minimum_quantity=0.001,
        trading_enabled=True,
        state=PRODUCT_STATE_ELIGIBLE,
        metadata={
            "synthetic_fallback": True,
            "synthetic_reason": "explicit-universe fallback; no venue "
                                "discovery; SPOT + precision assumed, "
                                "never verified",
        },
    )
    log.warning(
        "SYNTHETIC_INSTRUMENT symbol=%s product_type=SPOT assumed "
        "(unverified fallback; not derivative-realistic)",
        symbol,
    )
    return instrument


# =====================================================
# Builder
# =====================================================


def build_paper_engine(
    universe_manager=None,
    transport_factory=None,
    world_factory=None,
    clock=None,
    timeframe=None,
    strategy="",
    data_source=None,
    refresh_interval_seconds=60,
    starting_balance=None,
    journal=None,
    portfolio_manager=None,
    portfolio_state=None,
    universe_mode=None,
    registry=None,
    liquidity_provider=None,
    history_provider=None,
):
    """Assemble the canonical multi-symbol Phase 6E
    RealTimeEngine in PAPER mode.

    Every collaborator is injectable so the offline tests
    drive this exact build path; main.py uses the defaults:

      * universe_manager -- default selected by universe_mode:
          "provider" -> a canonical Phase 6B UniverseManager fed
                        by the real Delta liquidity/history
                        providers (Phase 9P-d); the eligibility
                        cascade decides the eligible cut.
          anything else / None -> ExplicitSymbolUniverseManager
                        (UNIVERSE="explicit" fallback: the
                        eligible cut is settings.SYMBOLS).
      * transport_factory -- RealTimeEngine default
        (DeltaSubscriptionStream, real network)
      * world_factory -- RealTimeEngine default
        (InstitutionalPipeline via default_world_factory)

    Provider-path injection (for offline tests): pass
    registry / liquidity_provider / history_provider to build
    the provider-backed manager without any network.

    Returns (engine, universe_manager) so the caller can
    inspect/`stop()` the engine.
    """

    effective_timeframe = timeframe or settings.TIMEFRAME

    effective_universe_mode = (
        universe_mode
        if universe_mode is not None
        else (getattr(settings, "UNIVERSE", "explicit") or "explicit")
    )

    manager = universe_manager
    if manager is None:
        if effective_universe_mode == "provider":
            manager, _registry, _liq, _hist = (
                build_provider_universe_manager(
                    registry=registry,
                    liquidity_provider=liquidity_provider,
                    history_provider=history_provider,
                    timeframe=effective_timeframe,
                )
            )
        else:
            manager = ExplicitSymbolUniverseManager(
                timeframe=effective_timeframe
            )

    effective_starting_balance = (
        starting_balance
        if starting_balance is not None
        else risk_settings.STARTING_BALANCE
    )

    # Phase 23: opt-in VERIFIED candle transport for the 6D seam.
    # The default transport factory stays FAIL-CLOSED (no ticker-derived
    # candles ever entered strategy logic); with QE_PAPER_VERIFIED_TRANSPORT
    # enabled the assembly binds the delivered verified public-candle
    # contract (finality + continuity + fail-closed dispatch) instead of
    # leaving the paper runtime transport-less. Paper-only; no order path
    # changes.
    if transport_factory is None:
        if (
            os.getenv("QE_PAPER_VERIFIED_TRANSPORT", "").strip().lower()
            in ("1", "true", "yes", "on")
        ):
            from data.realtime.verified_transport import (
                verified_public_candle_transport_factory,
            )

            transport_factory = verified_public_candle_transport_factory(
                resolution=effective_timeframe,
            )
            log.info(
                "PAPER verified candle transport ENABLED "
                "(opt-in via QE_PAPER_VERIFIED_TRANSPORT)"
            )

    from core.runtime.realtime_engine import RealTimeEngine

    engine = RealTimeEngine(
        universe_manager=manager,
        world_factory=world_factory,
        transport_factory=transport_factory,
        clock=clock,
        timeframe=effective_timeframe,
        strategy=strategy,
        data_source=data_source,
        refresh_interval_seconds=refresh_interval_seconds,
        starting_balance=effective_starting_balance,
        portfolio_manager=portfolio_manager,
        portfolio_state=portfolio_state,
        journal=journal,
    )

    return engine, manager


# =====================================================
# Drive loops
# =====================================================


def tick(engine, client=None, normalizer=None):
    """One non-blocking poll step (refresh-if-due then drain
    the live subscriptions). Returns whatever the poll did
    not (None) so callers can loop."""

    engine.poll(client=client, normalizer=normalizer)


def run_paper_forever(
    engine,
    poll_interval_seconds=10.0,
    client=None,
    normalizer=None,
):
    """Blocking poll loop for main.py: refresh the universe
    on cadence and drain closed-candle subscriptions until
    interrupted. The engine's subscription workers reconnect
    independently; one failure never kills the loop."""

    try:

        while True:

            engine.poll(client=client, normalizer=normalizer)

            time.sleep(poll_interval_seconds)

    except KeyboardInterrupt:

        log.info("paper runtime interrupted")

    finally:

        engine.stop()
