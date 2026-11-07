"""Fail-closed orchestration from Delta ob_updates frames to friction evidence.

This module deliberately has no socket/DNS/client dependency. A transport adapter
must supply decoded provider messages. The session binds the sequence-safe Phase-76
book state to the Phase-75 REAL capture recorder and refuses to finalize after any
continuity failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Iterable

from research.economics.delta_ws_friction_capture import DeltaOrderbookState
from research.economics.market_friction_capture import (
    CaptureIdentity,
    MarketFrictionCapture,
)
from research.economics.market_friction_evidence import MarketFrictionEvidenceArtifact


@dataclass(frozen=True, slots=True)
class CaptureSessionStats:
    messages_seen: int
    observations_emitted: int
    first_sequence: int | None
    last_sequence: int | None
    continuity_failures: int


class DeltaFrictionCaptureSession:
    """Bind decoded Delta order-book frames into one strict capture.

    Any provider/state error makes the session non-finalizable. The caller must
    start a fresh capture after resubscription/recovery; partial evidence is never
    presented as a continuous capture.
    """

    def __init__(self, identity: CaptureIdentity, *, alignment_ms: int = 1000):
        self.identity = identity
        self.book = DeltaOrderbookState(identity.symbol)
        self.capture = MarketFrictionCapture(identity, alignment_ms=alignment_ms)
        self._messages_seen = 0
        self._observations = 0
        self._first_sequence: int | None = None
        self._last_sequence: int | None = None
        self._continuity_failures = 0
        self._invalid = False

    @property
    def invalid(self) -> bool:
        return self._invalid

    @property
    def stats(self) -> CaptureSessionStats:
        return CaptureSessionStats(
            messages_seen=self._messages_seen,
            observations_emitted=self._observations,
            first_sequence=self._first_sequence,
            last_sequence=self._last_sequence,
            continuity_failures=self._continuity_failures,
        )

    def ingest(self, message: Mapping[str, Any]) -> None:
        if self._invalid:
            raise RuntimeError("capture session is invalid; start a fresh capture")
        self._messages_seen += 1
        try:
            observation = self.book.apply(message)
        except ValueError:
            self._continuity_failures += 1
            self._invalid = True
            raise
        if observation is None:
            return
        if self._first_sequence is None:
            self._first_sequence = observation.sequence
        self._last_sequence = observation.sequence
        sample = observation.to_sample()
        self.capture.add(
            timestamp_ms=sample["timestamp_ms"],
            best_bid=sample["best_bid"],
            best_ask=sample["best_ask"],
        )
        self._observations += 1

    def ingest_many(self, messages: Iterable[Mapping[str, Any]]) -> None:
        for message in messages:
            self.ingest(message)

    def finalize(self, *, captured_at: str | None = None) -> MarketFrictionEvidenceArtifact:
        if self._invalid:
            raise RuntimeError("invalid capture session cannot be finalized")
        if self._observations == 0:
            raise ValueError("capture session contains no orderbook observations")
        return self.capture.finalize(captured_at=captured_at)
