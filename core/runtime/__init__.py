"""
====================================================

QuantEngine

Runtime Package

Phase 6E -- Real-time integration (paper mode only).

The orchestration layer that wires the 6B universe refresh
and the 6D real-time closed-candle delivery into the frozen
6C SymbolPipeline, running continuously in paper mode:

    execution_port   -- the ONE paper/live execution seam
    pipeline_registry-- stable per-instrument pipeline
                        ownership (ADD / RETAIN / RETIRE)
    paper_runtime    -- per-instrument continuous paper unit
                        (frozen pipeline + BrokerEngine
                        dry-run + TradeRegistry ledger)
    realtime_engine  -- the orchestrator (refresh -> reconcile
                        -> subscription sync -> identity
                        routing)

Paper-only by construction: every runtime is wired with
dry_run=True through the PaperExecutionAdapter; zero
exchange writes.
====================================================
"""

from core.runtime.execution_port import (
    ExecutionPort,
    PaperExecutionAdapter,
    PaperOnlyError,
)
from core.runtime.paper_runtime import PaperRuntime
from core.runtime.pipeline_registry import (
    PipelineRegistry,
    instrument_identity_key,
)
from core.runtime.realtime_engine import RealTimeEngine

__all__ = [
    "ExecutionPort",
    "PaperExecutionAdapter",
    "PaperOnlyError",
    "PaperRuntime",
    "PipelineRegistry",
    "RealTimeEngine",
    "instrument_identity_key",
]