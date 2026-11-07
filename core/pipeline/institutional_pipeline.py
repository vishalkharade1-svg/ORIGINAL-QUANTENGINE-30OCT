"""
====================================================

Institutional Pipeline

Canonical Event-Driven Institutional Pipeline

====================================================
"""

from core.events.event_types import EventType
from core.pipeline.pipeline_statistics import PipelineStatistics

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.ema import EMA
from core.indicators.atr import ATR
from core.indicators.adx import ADX
from core.indicators.rsi import RSI

from core.trend.trend_engine import TrendEngine
from core.market_structure.engine import MarketStructureEngine

from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_target_engine import LiquidityTargetEngine

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner
from core.order_blocks.order_block_scanner import OrderBlockScanner

from core.regime.regime_engine import RegimeEngine

from core.order_blocks.order_block_lifecycle_engine import OrderBlockLifecycleEngine

from core.breaker.breaker_engine import BreakerEngine
from core.mitigation.mitigation_engine import MitigationEngine

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine

from core.execution.execution_engine import ExecutionEngine

from core.risk.risk_engine import RiskEngine

from core.pipeline.pipeline_debugger import PipelineDebugger

from core.common.logging_config import get_logger

from core.market_structure.swing_engine import SwingEngine
from core.market_structure.structure_engine import StructureEngine
from core.market_structure.bos_engine import BOSEngine
from core.market_structure.choch_engine import CHoCHEngine

log = get_logger(__name__)


class InstitutionalPipeline:

    DEBUG = False

    def log(self, *args, **kwargs):
        if self.DEBUG:
            print(*args, **kwargs)

    def __init__(
        self,
        context,
        statistics=None,
    ):

        self.context = context

        self.statistics = (
            statistics
            if statistics is not None
            else PipelineStatistics()
        )

        self.engines = []

        self.debugger = PipelineDebugger()

        # -------------------------------------------------
        # Indicator Engine
        # -------------------------------------------------

        self.indicators = IndicatorEngine()

        self.indicators.register(EMA(20))
        self.indicators.register(EMA(50))
        self.indicators.register(EMA(200))
        self.indicators.register(ATR(14))
        self.indicators.register(ADX(14))
        self.indicators.register(RSI(14))

        # Publish canonical indicator cache
        self.context.indicators = self.indicators.cache

        self.log(
            self.context.indicators.latest("EMA_20"),
            self.context.indicators.latest("ATR_14"),
        )

        # -------------------------------------------------
        # Register Institutional Pipeline
        # -------------------------------------------------

        self.register(TrendEngine())
        self.register(SwingEngine())
        self.register(StructureEngine())
        self.register(BOSEngine())
        self.register(CHoCHEngine())
        self.register(MarketStructureEngine())
        self.register(LiquidityPoolEngine())
        self.register(LiquidityTargetEngine())
        self.register(DisplacementScanner())
        self.register(FVGScanner())
        self.register(OrderBlockScanner())
        self.register(OrderBlockLifecycleEngine())
        self.register(BreakerEngine())
        self.register(MitigationEngine())
        self.register(RegimeEngine())
        self.register(TradeSetupBuilder())
        self.register(DecisionEngine())
        self.register(ExecutionEngine())
        self.register(RiskEngine())

    # ==========================================================

    def register(
        self,
        engine,
    ):

        if isinstance(engine, IndicatorEngine):

            log.error(
                "Ignoring register(%s): the IndicatorEngine is "
                "not a pipeline-engine stage. It owns the shared "
                "IndicatorCache and is driven directly by "
                "InstitutionalPipeline.process(). Registering a "
                "second one used to publish an empty cache into "
                "context.indicators every candle, silencing the "
                "entire pipeline.",
                engine.name,
            )

            return

        if any(
            e.name == engine.name
            for e in self.engines
        ):

            log.warning(
                "Ignoring register(%s): an engine with that "
                "name is already in the pipeline (one engine "
                "per stage -- Phase 4C duplicate-execution fix).",
                engine.name,
            )

            return

        if engine in self.engines:
            return

        self.engines.append(engine)

        self.engines.sort(
            key=lambda e: e.priority
        )

    # ----------------------------------------------------------

    def unregister(
        self,
        engine_name,
    ):

        self.engines = [

            engine

            for engine in self.engines

            if engine.name != engine_name

        ]

    # ==========================================================

    def subscribe(
        self,
        event_bus,
    ):

        event_bus.subscribe(
            EventType.CANDLE,
            self.on_candle,
        )

    # ==========================================================

    def on_candle(
        self,
        event,
    ):

        self.statistics.candle()

        self.context.add_candle(
            event.candle
        )

        self.process()

    # ==========================================================

    def process(self):

        # -------------------------------------------------
        # Reset per-candle outputs
        # -------------------------------------------------

        self.context.reset_cycle()

        bars = list(self.context.candles)
                # -------------------------------------------------
        # Indicators always execute first
        # -------------------------------------------------

        if bars:

            self.log(
                "Bars:",
                len(bars),
                bars[0].close,
                bars[-1].close,
            )

            self.indicators.update(bars)

            self.log("\nPIPELINE AFTER UPDATE")
            self.log(id(self.indicators.cache))
            self.log(self.indicators.cache.data.keys())

            # Publish canonical cache
            self.context.indicators = self.indicators.cache

            self.log("\nPIPELINE CACHE")

            self.log(
                "Context ID :",
                id(self.context)
            )

            self.log(
                "Cache ID   :",
                id(self.context.indicators)
            )

            self.log(
                "Keys       :",
                list(self.context.indicators.data.keys())
            )

            self.log(
                "EMA20:",
                self.context.indicators.latest("EMA_20"),
            )

            self.log(
                "ATR14:",
                self.context.indicators.latest("ATR_14"),
            )

        # -------------------------------------------------
        # Institutional Engines
        # -------------------------------------------------

        for engine in self.engines:

            if not engine.enabled:
                continue

            if not engine.validate(self.context):
                continue

            self.statistics.engine()

            engine.process(self.context)

            self.log(
                f"{engine.name:25}",
                {
                    "trend": self.context.trend is not None,
                    "swings": self.context.swings is not None,
                    "market_structure": (
                        self.context.market_structure is not None
                    ),
                    "liquidity": (
                        self.context.liquidity is not None
                    ),
                    "target": (
                        self.context.liquidity_target is not None
                    ),
                    "disp": (
                        self.context.displacement is not None
                    ),
                    "fvg": (
                        self.context.fvgs is not None
                    ),
                    "ob": (
                        self.context.order_blocks is not None
                    ),
                    "regime": (
                        self.context.regime is not None
                    ),
                    "setup": len(
                        self.context.trade_setups or []
                    ),
                    "decision": (
                        len(self.context.decision.all())
                        if self.context.decision
                        else 0
                    ),
                },
            )

        self.context.completed = True

        self.log("\nBEFORE DEBUGGER")

        self.log(
            "Context ID :",
            id(self.context)
        )

        self.log(
            "Cache ID   :",
            id(self.context.indicators)
        )

        self.log(
            "Keys       :",
            list(self.context.indicators.data.keys())
        )

        self.log(
            "EMA20:",
            self.context.indicators.latest("EMA_20"),
        )

        self.log(
            "ATR14:",
            self.context.indicators.latest("ATR_14"),
        )

        if self.DEBUG:
            self.debugger.dump(self.context)

    # ==========================================================

    def reset(self):

        self.statistics.reset()

        self.context.reset()

        self.indicators.reset()

        # Re-link the shared cache. context.reset() nulls
        # context.indicators; the IndicatorCache must never
        # remain detached from the IndicatorEngine that owns it.
        self.context.indicators = self.indicators.cache

        for engine in self.engines:

            engine.reset()