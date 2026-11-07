import asyncio

from config.settings import settings

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus

from data.websocket_client import start

async def main():

    # -------------------------------------------------
    # Shared Objects (legacy / live-analyze path)
    #
    # Phase 2 fail-closed: `market` below is a single-symbol
    # mark-price REFERENCE ONLY (SYMBOLS[0]).  It is NOT an
    # authoritative OHLCV source and no strategy candle may be
    # derived from it.  The verified multi-symbol traded-candle
    # transport (data/delta/verified_socket_transport.py) is the
    # only future strategy feed; until its Global evidence gate
    # passes, LIVE/ANALYZE strategy execution stays disabled and
    # this feed only maintains reference prices.
    # -------------------------------------------------

    context = PipelineContext()

    market = MarketState(
        symbol=settings.SYMBOLS[0],
        timeframe=settings.TIMEFRAME,
    )

    event_bus = EventBus()

    # InstitutionalPipeline registers the full institutional
    # engine set (indicators, trend, swings, structure,
    # liquidity, displacement, FVG, order blocks, regime,
    # setup, decision, execution) internally in __init__.
    #
    # Do NOT re-register any of those here: doing so used to
    # add a second, unconfigured IndicatorEngine into the
    # pipeline (priority=10, runs first, no EMA/ATR/ADX/RSI
    # registered on it) whose analyze() call overwrote the
    # correctly-populated context.indicators with an empty
    # cache on every candle -- which is what caused every
    # downstream engine (starting with DisplacementScanner's
    # ATR check) to silently produce zero output. See the
    # audit notes for the full trace.

    pipeline = InstitutionalPipeline(context)

    # -------------------------------------------------
    # Subscribe Pipeline
    #
    # Phase 11A: the execution mode is resolved ONCE via
    # ExecutionMode.resolve -- PAPER+LIVE conflict and
    # unknown EXECUTION_MODE values fail closed with
    # ConfigurationError (no silent PAPER-wins, no silent
    # analyze-only fall-through). The safety banner below
    # is the auditable startup record (no secrets).
    #
    # PAPER MODE (default): the CANONICAL multi-symbol Phase
    # 6E RealTimeEngine runtime (closed-candle delivery routed
    # by (exchange, instrument_id) to each instrument's own
    # PipelineRegistry -> PaperRuntime -> BrokerEngine
    # dry-run stack). See core/runtime/paper_main.py. No API
    # keys are required. Paper-only by construction.
    #
    # LIVE MODE: a BrokerEngine subscribes instead and drives
    # the same pipeline-first flow, routing RiskEngine
    # intents to the real Delta exchange via a
    # DeltaOrderExecutor. Requires ALL of mode == LIVE,
    # ALLOW_LIVE=true, LIVE_EXECUTE=1 and valid
    # DELTA_API_KEY/SECRET (LiveSafetyGate) -- otherwise
    # startup REFUSES with LiveBlockedError and nothing is
    # placed, downgraded, or fallen through.
    #
    # ANALYZE-ONLY: the explicit no-fills state (neither
    # mode flag set) -- the pipeline subscribes directly,
    # every engine runs live but no fills or bookings
    # happen.
    # -------------------------------------------------

    from core.execution.live_safety_gate import (
        ExecutionMode,
        LiveSafetyGate,
    )

    mode = ExecutionMode.resolve(
        paper_mode=settings.PAPER_MODE,
        live_mode=settings.LIVE_MODE,
        execution_mode=getattr(
            settings, "EXECUTION_MODE", ""
        ),
    )

    _gate_inputs = LiveSafetyGate.from_settings(mode=mode)

    if mode == ExecutionMode.LIVE:

        _safety = LiveSafetyGate.require(
            component="main.startup",
            **_gate_inputs,
        )

    else:

        _safety = LiveSafetyGate.decide(**_gate_inputs)

    for _banner_line in LiveSafetyGate.format_banner(_safety):
        print(_banner_line)

    if mode == ExecutionMode.PAPER:

        from core.runtime.paper_main import build_paper_engine

        from core.monitoring.service import run_paper_with_monitoring

        engine, _manager = build_paper_engine()

        print("\n" + "=" * 60)
        print("QuantEngine Started")
        print("=" * 60)
        print(f"Symbols   : {settings.SYMBOLS}")
        print("Mode      : PAPER TRADING (multi-symbol runtime)")
        print("Runtime   : Phase 6E RealTimeEngine")
        print("Strategy  : InstitutionalPipeline (frozen system)")
        print("Paper-only: dry_run=True, zero exchange writes")
        print(
            "Control API: "
            + (
                "ENABLED (localhost, token-protected, PAPER-only)"
                if (
                    getattr(settings, "CONTROL_API_ENABLED", False)
                    and getattr(settings, "CONTROL_API_TOKEN", "")
                )
                else "disabled (default)"
            )
        )
        print("=" * 60)
        print("Waiting for live candles...\n")

        # Phase 9P-g: the PAPER entrypoint drives the engine through
        # an authoritative EngineLifecycle (which owns the poll loop)
        # and optionally starts the Control & Monitoring API around
        # the SAME engine. Disabled by default -> behaviour matches
        # the pre-9P-g run_paper_forever loop. The API (when enabled)
        # can issue PAPER-only start/stop/restart/emergency_stop; a
        # /control/stop cleanly ends this loop and shuts everything
        # down. run_paper_forever remains available for callers that
        # drive the loop directly.
        run_paper_with_monitoring(engine)

        return

    elif mode == ExecutionMode.LIVE:

        from core.live.broker_engine import BrokerEngine

        from core.exchanges.delta.delta_contract_loader import (
            DeltaContractLoader,
        )
        from core.exchanges.delta.delta_exchange import DeltaExchange

        from core.execution.order_executor import DeltaOrderExecutor

        executor = DeltaOrderExecutor(
            exchange=DeltaExchange(),
            registry=DeltaContractLoader().load(),
        )

        # Stage 1-3 hardening: live trading is unverified without
        # position reconciliation. The reconciler journals broker
        # state (data/runtime/broker_state.json) and halts new
        # orders on any local-vs-exchange divergence until an
        # operator explicitly resolves it.
        from core.live.reconciler import Reconciler

        broker = BrokerEngine(
            pipeline,
            event_bus,
            executor=executor,
            dry_run=False,
            safety=_safety,
            reconciler=Reconciler(
                executor=executor,
                snapshot_path="data/runtime/broker_state.json",
            ),
        )

        broker.subscribe(event_bus)

    else:

        pipeline.subscribe(event_bus)

    print("\n" + "=" * 60)
    print("QuantEngine Started")
    print("=" * 60)
    print(f"Symbol    : {settings.SYMBOLS[0]} (mark-price reference only)")
    if mode == ExecutionMode.PAPER:

        print("Mode      : PAPER TRADING")

    elif mode == ExecutionMode.LIVE:

        print("Mode      : LIVE TRADING (gate-ARMED)")

    else:

        print("Mode      : LIVE ANALYZE-ONLY")

    print("Strategy candles: DISABLED (legacy ticker-mark path removed;")
    print("  verified Global traded-candle transport evidence required)")
    print("Mark-price feed : reference-only (never authoritative OHLCV)")
    print("Waiting for live candles...\n")

    # -------------------------------------------------
    # Start Live Feed (reference-only)
    #
    # Phase 2: publish_candles defaults to False, so this feed
    # maintains MarketState mark-price reference fields only and
    # delivers ZERO strategy candles to the pipeline/broker until
    # the verified Global transport is evidenced and wired.  Do NOT
    # pass publish_candles=True from any production entry point.
    # -------------------------------------------------

    await start(

        event_bus=event_bus,

        market=market,

    )


if __name__ == "__main__":

    asyncio.run(main())