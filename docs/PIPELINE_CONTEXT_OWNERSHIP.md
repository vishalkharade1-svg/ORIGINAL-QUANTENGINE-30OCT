# ============================================================
# QuantEngine
# PIPELINE CONTEXT OWNERSHIP
# ============================================================

Architecture Version : 1.0.5

Status : ACTIVE

Last Updated : Sprint 8

============================================================

PURPOSE

This document is the ONLY authority for PipelineContext.

Every context variable MUST be registered here.

No engine may create new context variables unless this
document is updated first.

============================================================
RULES
============================================================

OWNER

The only engine allowed to WRITE this variable.

READERS

Engines allowed to READ the variable.

WRITE ACCESS

Exactly ONE owner.

READ ACCESS

Unlimited.

============================================================
SYSTEM
============================================================

completed

Owner

InstitutionalPipeline

Readers

All

------------------------------------------------------------

market

Owner

WebSocketClient
Backtester

Readers

All

------------------------------------------------------------

candles

Owner

InstitutionalPipeline

Readers

All

============================================================
INDICATORS
============================================================

indicators

Type

IndicatorCache

Owner

IndicatorEngine

Readers

TrendEngine

MarketStructureEngine

LiquidityPoolEngine

LiquidityTargetEngine

DisplacementScanner

FVGScanner

OrderBlockScanner

RegimeEngine

TradeSetupBuilder

DecisionEngine

ExecutionEngine

NOTE

This replaces every previous name such as

indicator_cache

cache

indicator_data

Only "indicators" is legal.

============================================================
TREND
============================================================

trend

Owner

TrendEngine

Readers

RegimeEngine

TradeSetupBuilder

DecisionEngine

ExecutionEngine

============================================================
MARKET STRUCTURE
============================================================

market_structure

Owner

MarketStructureEngine

Readers

LiquidityPoolEngine

LiquidityTargetEngine

RegimeEngine

TradeSetupBuilder

============================================================
LIQUIDITY
============================================================

buy_liquidity

Owner

LiquidityPoolEngine

Readers

LiquidityTargetEngine

------------------------------------------------------------

sell_liquidity

Owner

LiquidityPoolEngine

Readers

LiquidityTargetEngine

------------------------------------------------------------

liquidity_target

Owner

LiquidityTargetEngine

Readers

TradeSetupBuilder

DecisionEngine

============================================================
DISPLACEMENT
============================================================

displacement

Owner

DisplacementScanner

Readers

FVGScanner

OrderBlockScanner

RegimeEngine

TradeSetupBuilder

============================================================
FAIR VALUE GAPS
============================================================

fvg

Owner

FVGScanner

Readers

OrderBlockScanner

RegimeEngine

TradeSetupBuilder

============================================================
ORDER BLOCKS
============================================================

order_blocks

Owner

OrderBlockScanner

Readers

RegimeEngine

TradeSetupBuilder

============================================================
REGIME
============================================================

regime

Owner

RegimeEngine

Readers

TradeSetupBuilder

DecisionEngine

ExecutionEngine

============================================================
TRADE SETUPS
============================================================

trade_setups

Owner

TradeSetupBuilder

Readers

DecisionEngine

ExecutionEngine

============================================================
DECISION
============================================================

decision

Owner

DecisionEngine

Readers

ExecutionEngine

============================================================
EXECUTION
============================================================

execution_signal

Owner

ExecutionEngine

Readers

TradeSimulator

PaperTrading

BrokerEngine

============================================================
SIMULATION
============================================================

trade_result

Owner

TradeSimulator

Readers

Portfolio

Analytics

============================================================
PORTFOLIO
============================================================

portfolio

Owner

PortfolioEngine

Readers

Analytics

Optimization

AI

============================================================
BACKTEST
============================================================

backtest_result

Owner

Backtester

Readers

Optimization

Analytics

============================================================
OPTIMIZATION
============================================================

optimization_result

Owner

OptimizationEngine

Readers

AI

Mobile

============================================================
AI
============================================================

ai_score

Owner

AIEngine

Readers

DecisionEngine

============================================================
PROHIBITED VARIABLES
============================================================

The following names SHALL NEVER exist inside PipelineContext.

indicator_cache

indicator_data

cache

trend_data

market

market_info

current_market

current_trend

setup

setup_registry

decision_registry

execution

signal

============================================================
CHANGE POLICY
============================================================

Before adding ANY PipelineContext variable:

1.

Update this document.

2.

Update PROJECT_MANIFEST.md

3.

Update IMPORT_MANIFEST.md

4.

Update PIPELINE_DEPENDENCY_GRAPH.md

5.

Update tests.

Only then may the code be modified.

============================================================
END
============================================================