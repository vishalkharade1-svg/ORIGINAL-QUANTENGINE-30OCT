"""Verified Delta public data -> canonical strategy runtime (E2E link).

This module composes the already-delivered Delta front-end parts into the
one previously missing end-to-end boundary: released public frames can now
reach the canonical strategy runtime (InstitutionalPipeline) but ONLY after
passing, in order, every delivered gate:

1. ``DeltaPublicEventStream`` normalization + authoritative state/finality/
   continuity tracking;
2. ``ClosedCandleRouter`` causal-candle filtering (forming/rejected/
   duplicate/non-candle frames never reach the consumer);
3. ``to_runtime_candle`` fail-closed conversion to the legacy ``Candle``
   (resolution, traded price basis, reported volume, start timestamp);
4. ``MarketStateStore.snapshot`` authoritative market state;
5. ``VerifiedStrategyDispatcher`` authoritative-data + closed-candle gate.

Every rejection is counted with its reason; nothing is manufactured (no
synthetic candles, no inferred volume, no guessed events). The adapter owns
no network transport and no credentials: it is caller-driven, exactly like
the public event stream it wraps.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from core.events.candle_event import CandleEvent
from data.delta.closed_candle_router import ClosedCandleRouter
from data.delta.market_events import NormalizedCandle
from data.delta.public_event_stream import DeltaPublicEventStream, IngestResult
from data.delta.runtime_candle_bridge import RuntimeCandleDecision, to_runtime_candle
from data.delta.verified_strategy_dispatch import (
    StrategyDispatchRecord,
    VerifiedStrategyDispatcher,
)


@dataclass(frozen=True, slots=True)
class RuntimeProvenance:
    """Audit trail for one operator-facing record's source frames.

    ``receipt_timestamp`` is the caller-supplied receipt time of the frame
    that produced the record (never dropped).  ``candle_timestamp`` is the
    delivered strategy candle's start when the frame produced one;
    ``trigger_candle_timestamp`` is the normalized start of the frame that
    closed the previous candle (continuity proof input).
    """

    receipt_timestamp: int | None
    candle_timestamp: int | None
    trigger_candle_timestamp: int | None


@dataclass(frozen=True, slots=True)
class RuntimeIngestRecord:
    """One operator-facing decision record for one ingested public frame."""

    ingest_status: str
    ingest_event_type: str
    ingest_reason: str
    routed_to_runtime: bool
    runtime_rejection: str | None
    delivered_to_strategy: bool
    dispatch_record: StrategyDispatchRecord | None
    venue: str | None
    instrument: str | None
    resolution: str | None
    candle_start_timestamp: int | None
    provenance: RuntimeProvenance


@dataclass(frozen=True, slots=True)
class _FrameContext:
    result: IngestResult
    norm: NormalizedCandle | None = None


class DeltaStrategyRuntimeAdapter:
    """Delivery-only composition; no network transport, no credentials.

    Callers feed already-received public frames with their receipt time and
    obtain a per-frame record. Whenever the frame yields a causally closed,
    continuous, subscription-resolution, traded-price candle with reported
    volume and a passing authoritative snapshot, the canonical strategy
    runtime receives one ``CandleEvent`` and runs one pipeline cycle.
    """

    def __init__(
        self,
        pipeline,
        *,
        expected_resolution: str = "1m",
        require_volume: bool = True,
    ) -> None:
        if pipeline is None:
            raise ValueError(
                "canonical strategy runtime is required: no pipeline, no delivery"
            )
        if not isinstance(require_volume, bool):
            raise ValueError("require_volume must be a boolean")
        if not require_volume:
            raise ValueError("the authoritative volume gate cannot be disabled")
        self._pipeline = pipeline
        self._expected_resolution = expected_resolution
        self._stream = DeltaPublicEventStream()
        self._router = ClosedCandleRouter(self._runtime_consumer)
        self._dispatch = VerifiedStrategyDispatcher(
            self._strategy_callback, on_decision=self._on_dispatch_decision,
        )
        self._records: list[RuntimeIngestRecord] = []
        self._delivered: list[CandleEvent] = []
        self._runtime_rejections: Counter[str] = Counter()
        self._last_dispatch: StrategyDispatchRecord | None = None
        self._last_runtime_rejection: str | None = None
        self._frame_context: _FrameContext | None = None
        self._last_receipt: int | None = None

    def ingest_frame(self, frame: Any, *, receipt_timestamp: Any) -> RuntimeIngestRecord:
        result = self._stream.ingest(frame, receipt_timestamp=receipt_timestamp)
        try:
            self._last_receipt = int(receipt_timestamp)
        except (TypeError, ValueError):
            self._last_receipt = None
        self._last_dispatch = None
        self._last_runtime_rejection = None
        closed = result.closed_candle
        self._frame_context = _FrameContext(result=result, norm=closed)
        before = len(self._records)
        self._router.route(result)
        if len(self._records) == before:
            self._append(result, routed=False, delivered=False)
        return self._records[-1]

    # ------------------------------------------------------------------
    # composition stages (invoked synchronously within ingest_frame)
    # ------------------------------------------------------------------

    def _runtime_consumer(self, candle: NormalizedCandle) -> None:
        context = self._frame_context
        if context is None:  # pragma: no cover - router-only synchronous path
            raise AssertionError("router consumer invoked outside ingest_frame")
        result = context.result
        decision: RuntimeCandleDecision = to_runtime_candle(
            result, expected_resolution=self._expected_resolution,
        )
        if decision.candle is None:
            self._last_runtime_rejection = decision.reason
            self._runtime_rejections[decision.reason] += 1
            if candle is not None:
                self._append(result, routed=True, delivered=False, norm=candle)
            else:
                self._append(result, routed=False, delivered=False)
            return
        self._last_runtime_rejection = None
        provenance = candle.provenance
        state = self._stream.store.snapshot(provenance.venue, provenance.instrument)
        gate_decision = self._dispatch.dispatch(decision.candle, state)
        dispatch_record = self._last_dispatch
        self._append(
            result,
            routed=True,
            delivered=bool(gate_decision.allowed),
            norm=candle,
            dispatch_record=dispatch_record,
            candle_timestamp=decision.candle.timestamp,
        )

    def _strategy_callback(self, candle) -> None:
        event = CandleEvent(
            candle=candle,
            symbol=candle.symbol,
            timeframe=self._expected_resolution,
        )
        self._delivered.append(event)
        self._pipeline.on_candle(event)

    def _on_dispatch_decision(self, record: StrategyDispatchRecord) -> None:
        self._last_dispatch = record
        if record.allowed:
            return
        self._runtime_rejections[record.reason] += 1

    # ------------------------------------------------------------------
    # per-frame record
    # ------------------------------------------------------------------

    def _append(
        self,
        result: IngestResult,
        *,
        routed: bool,
        delivered: bool,
        norm: NormalizedCandle | None = None,
        dispatch_record: StrategyDispatchRecord | None = None,
        candle_timestamp: int | None = None,
    ) -> None:
        provenance = norm.provenance if norm is not None else None
        self._records.append(RuntimeIngestRecord(
            ingest_status=result.status,
            ingest_event_type=result.event_type,
            ingest_reason=result.reason,
            routed_to_runtime=routed,
            runtime_rejection=self._last_runtime_rejection,
            delivered_to_strategy=delivered,
            dispatch_record=dispatch_record,
            venue=provenance.venue if provenance else None,
            instrument=provenance.instrument if provenance else None,
            resolution=norm.resolution if norm is not None else None,
            candle_start_timestamp=(
                norm.candle_start_timestamp if norm is not None else None
            ),
            provenance=RuntimeProvenance(
                receipt_timestamp=self._last_receipt,
                candle_timestamp=candle_timestamp,
                trigger_candle_timestamp=(
                    norm.candle_start_timestamp if norm is not None else None
                ),
            ),
        ))

    # ------------------------------------------------------------------
    # observability
    # ------------------------------------------------------------------

    def delivered_events(self) -> tuple[CandleEvent, ...]:
        return tuple(self._delivered)

    def ingest_records(self) -> tuple[RuntimeIngestRecord, ...]:
        return tuple(self._records)

    def stats(self) -> dict:
        return {
            "stream": self._stream.stats(),
            "router": {
                "delivered": self._router.delivered,
                "suppressed": self._router.suppressed,
            },
            "dispatch": self._dispatch.stats(),
            "events_delivered_to_strategy": len(self._delivered),
            "runtime_rejections": dict(self._runtime_rejections),
        }
