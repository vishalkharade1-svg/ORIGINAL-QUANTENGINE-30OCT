# ============================================================
# QuantEngine
# PIPELINE DEPENDENCY GRAPH
# ============================================================

Architecture Version : 1.0.6

Status : ACTIVE

Last Updated : Sprint 8

============================================================
PURPOSE
============================================================

This document defines the ONLY legal execution order of the
Institutional Pipeline.

Every engine must appear exactly once.

Every engine has:

• Inputs
• Outputs
• Dependencies
• Priority

No engine may read data that has not yet been produced.

============================================================
PIPELINE OVERVIEW
============================================================

                    Live / Replay Data
                           │
                           ▼
                   Candle Builder
                           │
                           ▼
                 Institutional Pipeline
                           │
                           ▼
                 Indicator Engine
                           │
                           ▼
                   Trend Engine
                           │
                           ▼
             Market Structure Engine
                           │
                           ▼
             Liquidity Pool Engine
                           │
                           ▼
           Liquidity Target Engine
                           │
                           ▼
             Displacement Scanner
                           │
                           ▼
                 FVG Scanner
                           │
                           ▼
             Order Block Scanner
                           │
                           ▼
                 Regime Engine
                           │
                           ▼
             Trade Setup Builder
                           │
                           ▼
               Decision Engine
                           │
                           ▼
              Execution Engine
                           │
                           ▼
              Trade Simulator
                           │
                           ▼
               Portfolio Engine
                           │
                           ▼
             Performance Analytics
                           │
                           ▼
             Optimization Engine
                           │
                           ▼
                   AI Engine

============================================================
ENGINE EXECUTION ORDER
============================================================

------------------------------------------------------------
10
IndicatorEngine
------------------------------------------------------------

Consumes

context.candles

Produces

context.indicators

Dependencies

None

------------------------------------------------------------
20
TrendEngine
------------------------------------------------------------

Consumes

context.candles

context.indicators

Produces

context.trend

Dependencies

IndicatorEngine

------------------------------------------------------------
30
MarketStructureEngine
------------------------------------------------------------

Consumes

context.candles

Produces

context.market_structure

Dependencies

IndicatorEngine

------------------------------------------------------------
40
LiquidityPoolEngine
------------------------------------------------------------

Consumes

context.market_structure

Produces

context.buy_liquidity

context.sell_liquidity

Dependencies

MarketStructureEngine

------------------------------------------------------------
50
LiquidityTargetEngine
------------------------------------------------------------

Consumes

context.buy_liquidity

context.sell_liquidity

Produces

context.liquidity_target

Dependencies

LiquidityPoolEngine

------------------------------------------------------------
60
DisplacementScanner
------------------------------------------------------------

Consumes

context.candles

context.indicators

Produces

context.displacement

Dependencies

IndicatorEngine

------------------------------------------------------------
70
FVGScanner
------------------------------------------------------------

Consumes

context.candles

context.displacement

Produces

context.fvg

Dependencies

DisplacementScanner

------------------------------------------------------------
80
OrderBlockScanner
------------------------------------------------------------

Consumes

context.candles

context.displacement

context.fvg

Produces

context.order_blocks

Dependencies

FVGScanner

------------------------------------------------------------
90
RegimeEngine
------------------------------------------------------------

Consumes

context.trend

context.market_structure

context.indicators

context.displacement

context.fvg

context.order_blocks

Produces

context.regime

Dependencies

TrendEngine

MarketStructureEngine

OrderBlockScanner

------------------------------------------------------------
100
TradeSetupBuilder
------------------------------------------------------------

Consumes

context.regime

context.order_blocks

context.liquidity_target

context.fvg

Produces

context.trade_setups

Dependencies

RegimeEngine

------------------------------------------------------------
110
DecisionEngine
------------------------------------------------------------

Consumes

context.trade_setups

Produces

context.decision

Dependencies

TradeSetupBuilder

------------------------------------------------------------
120
ExecutionEngine
------------------------------------------------------------

Consumes

context.decision

Produces

context.execution_signal

Dependencies

DecisionEngine

------------------------------------------------------------
130
TradeSimulator
------------------------------------------------------------

Consumes

context.execution_signal

Produces

context.trade_result

Dependencies

ExecutionEngine

------------------------------------------------------------
140
PortfolioEngine
------------------------------------------------------------

Consumes

context.trade_result

Produces

context.portfolio

Dependencies

TradeSimulator

------------------------------------------------------------
150
PerformanceAnalytics
------------------------------------------------------------

Consumes

context.portfolio

Produces

context.backtest_result

Dependencies

PortfolioEngine

------------------------------------------------------------
160
OptimizationEngine
------------------------------------------------------------

Consumes

context.backtest_result

Produces

context.optimization_result

Dependencies

PerformanceAnalytics

------------------------------------------------------------
170
AIEngine
------------------------------------------------------------

Consumes

context.optimization_result

context.regime

context.trade_setups

Produces

context.ai_score

Dependencies

OptimizationEngine

============================================================
PIPELINE RULES
============================================================

1.

Only one engine owns each PipelineContext variable.

2.

No engine may overwrite another engine's output.

3.

Every engine must validate required inputs before processing.

4.

Execution order is fixed by priority.

5.

Replay and Live pipelines must execute the exact same engine
sequence.

6.

Optimization, Paper Trading and Live Trading MUST use this
same pipeline.

============================================================
END
============================================================