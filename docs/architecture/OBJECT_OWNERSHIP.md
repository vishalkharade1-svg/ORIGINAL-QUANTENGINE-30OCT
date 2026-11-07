====================================================
QUANTENGINE
OBJECT OWNERSHIP
====================================================

Architecture Version : 1.0.8
Status               : ACTIVE
Last Updated         : Sprint Architecture Migration AM-0001

====================================================
PURPOSE
====================================================

This document defines the ownership of every major
object in QuantEngine.

Every object has ONE owner.

Only the owner may modify the object.

Other modules may READ the object but must never
modify it.

====================================================
OBJECT
====================================================

PipelineContext

Owner
----------------------------------------------------

InstitutionalPipeline

Stored In
----------------------------------------------------

Runtime

Read By
----------------------------------------------------

All Engines

Write By
----------------------------------------------------

InstitutionalPipeline ONLY

====================================================
OBJECT
====================================================

IndicatorEngine

Owner
----------------------------------------------------

InstitutionalPipeline

Stored In
----------------------------------------------------

InstitutionalPipeline.indicators

Read By
----------------------------------------------------

InstitutionalPipeline ONLY

Write By
----------------------------------------------------

InstitutionalPipeline ONLY

====================================================
OBJECT
====================================================

IndicatorCache

Owner
----------------------------------------------------

IndicatorEngine

Stored In
----------------------------------------------------

PipelineContext.indicators

Read By
----------------------------------------------------

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

Backtester

Paper Trading

Live Trading (BrokerEngine)

Replay Engine

Optimizer

AI Layer

Write By
----------------------------------------------------

IndicatorEngine ONLY

====================================================
OBJECT
====================================================

TrendState

Owner
----------------------------------------------------

TrendEngine

Stored In
----------------------------------------------------

PipelineContext.trend

Read By
----------------------------------------------------

RegimeEngine

TradeSetupBuilder

DecisionEngine

ExecutionEngine

Write By
----------------------------------------------------

TrendEngine ONLY

====================================================
OBJECT
====================================================

Market Structure

Owner
----------------------------------------------------

MarketStructureEngine

Stored In
----------------------------------------------------

PipelineContext.structure

Read By
----------------------------------------------------

Liquidity Engines

RegimeEngine

TradeSetupBuilder

DecisionEngine

Write By
----------------------------------------------------

MarketStructureEngine ONLY

====================================================
OBJECT
====================================================

Liquidity

Owner
----------------------------------------------------

Liquidity Engines

Stored In
----------------------------------------------------

PipelineContext.liquidity

Read By
----------------------------------------------------

TradeSetupBuilder

DecisionEngine

Write By
----------------------------------------------------

Liquidity Engines ONLY

====================================================
OBJECT
====================================================

Displacement

Owner
----------------------------------------------------

DisplacementScanner

Stored In
----------------------------------------------------

PipelineContext.displacement

Read By
----------------------------------------------------

FVGScanner

OrderBlockScanner

TradeSetupBuilder

Write By
----------------------------------------------------

DisplacementScanner ONLY

====================================================
OBJECT
====================================================

Fair Value Gaps

Owner
----------------------------------------------------

FVGScanner

Stored In
----------------------------------------------------

PipelineContext.fvgs

Read By
----------------------------------------------------

TradeSetupBuilder

DecisionEngine

Write By
----------------------------------------------------

FVGScanner ONLY

====================================================
OBJECT
====================================================

Order Blocks

Owner
----------------------------------------------------

OrderBlockScanner

Stored In
----------------------------------------------------

PipelineContext.order_blocks

Read By
----------------------------------------------------

TradeSetupBuilder

DecisionEngine

ExecutionEngine

Write By
----------------------------------------------------

OrderBlockScanner ONLY

====================================================
OBJECT
====================================================

Regime

Owner
----------------------------------------------------

RegimeEngine

Stored In
----------------------------------------------------

PipelineContext.regime

Read By
----------------------------------------------------

TradeSetupBuilder

DecisionEngine

Write By
----------------------------------------------------

RegimeEngine ONLY

====================================================
OBJECT
====================================================

Trade Setup Registry

Owner
----------------------------------------------------

TradeSetupBuilder

Stored In
----------------------------------------------------

PipelineContext.trade_setups

Read By
----------------------------------------------------

DecisionEngine

Write By
----------------------------------------------------

TradeSetupBuilder ONLY

====================================================
OBJECT
====================================================

Decision

Owner
----------------------------------------------------

DecisionEngine

Stored In
----------------------------------------------------

PipelineContext.decision

Read By
----------------------------------------------------

ExecutionEngine

Backtester

Paper Trading

Write By
----------------------------------------------------

DecisionEngine ONLY

====================================================
OBJECT
====================================================

Execution Signal

Owner
----------------------------------------------------

ExecutionEngine

Stored In
----------------------------------------------------

PipelineContext.order

Read By
----------------------------------------------------

Broker

Paper Trading

Backtester

Mobile Dashboard

Write By
----------------------------------------------------

ExecutionEngine ONLY

====================================================
RULES
====================================================

1. Every object has exactly ONE owner.

2. Only the owner may modify the object.

3. All other modules are read-only consumers.

4. New architecture objects must be added to this
document before implementation.

5. Any ownership change requires an Architecture
Migration (AM).

6. Every Change Request (CR) must reference this
document before modifying a shared object.

====================================================
END OF DOCUMENT
====================================================