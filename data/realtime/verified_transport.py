"""Phase 6D transport seam backed by the DELIVERED verified public-candle contract.

``MultiSymbolSubscriptionManager`` documents its transport contract as:

    transport.subscribe(symbol, on_candle, on_down) -> None  (raises on failure)
    transport.unsubscribe(symbol)                   -> None
    transport.close()                               -> None

and its production default fails closed awaiting exactly this binding:

    "A future socket implementation may replace this only after it is
     bound to the verified public-candle contract for the configured
     venue and symbols."

This module is that binding for PAPER mode.  It is caller-driven: it owns
no network transport and no credentials -- the operator's socket pump
feeds ``ingest(frame, receipt_timestamp=...)`` and the transport forwards
only what the verified Phase-1..22 chain admits:

* every CLOSED strategy candle flows through ``DeltaPublicEventStream``
  (finality + continuity) and ``to_runtime_candle`` (fail-closed
  verification: resolution, traded price basis, reported volume, start
  timestamp) -- identical to the Phase-22 ``DeltaStrategyRuntimeAdapter``
  conversion;
* FORMING frames deliver freshness ticks only, built verbatim from the
  raw frame via the delivered normalizer, tagged ``closed=False`` -- the
  6D worker explicitly keeps health fresh on forming ticks and its own
  router drops them before strategy logic ever sees them;
* mark-price, volume-unavailable, continuity-broken, duplicate and
  unhandled frames NEVER yield a delivered candle.  Nothing is
  manufactured: no synthetic candles, no inferred volume, no guessed
  events.  Every rejection is counted and observable via ``stats()``.

Phase 24 additions (harness-verified):

* ``notify_down`` now tears down the affected registrations after
  fanning out ``on_down``: the subscription ceases to exist exactly
  like the socket that died.  Frames arriving while a symbol is torn
  down are counted ``unrouted`` (fail-closed; never queued for late
  delivery) and the 6D worker's scheduled reconnect retry re-subscribes
  through the ordinary ``subscribe`` seam, restoring LIVE delivery.
  (The Phase-23 form retained the registration, which made the
  documented worker reconnect path impossible: every retry failed with
  "already registered" forever -- P24-1.)
* ``repair_gap_history`` exposes the delivered stream gap-repair path
  (``DeltaPublicEventStream.repair_historical_candles``) to the paper
  seam.  It validates against OUTSTANDING gaps only, appends repaired
  candles to the normalized event journal and restores continuity
  state; it never routes a repaired candle to strategy logic.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from core.history.candle import Candle
from data.delta.market_events import (
    InvalidMarketFrame,
    normalize_candlestick_frame,
)
from data.delta.public_event_stream import DeltaPublicEventStream
from data.delta.runtime_candle_bridge import to_runtime_candle


class VerifiedPublicCandleTransport:
    """Multiplexed 6D transport over the verified public-candle contract.

    The underlying verified stream is shared (one normalization /
    finality / continuity authority), while deliveries are scoped strictly
    per registered symbol handler.
    """

    def __init__(self, *, resolution: str = "1m") -> None:
        self._resolution = resolution
        self._stream = DeltaPublicEventStream()
        self._subscriptions: dict[
            str,
            tuple[Callable[[Any], None], Callable[[], None]],
        ] = {}
        self._frames_ingested = 0
        self._forming_delivered = 0
        self._closed_delivered = 0
        self._unrouted = 0
        self._rejections: Counter[str] = Counter()

    # ------------------------------------------------------------------
    # 6D transport seam
    # ------------------------------------------------------------------

    def subscribe(
        self,
        symbol: str,
        on_candle: Callable[[Any], None],
        on_down: Callable[[], None],
    ) -> None:
        """Register one logical subscription (raises on failure, so the
        worker's own lifecycle retries it)."""
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(
                "verified transport requires a non-empty symbol string"
            )
        if not callable(on_candle) or not callable(on_down):
            raise ValueError(
                "verified transport requires callable candle/down callbacks"
            )
        if symbol in self._subscriptions:
            raise ValueError(
                "symbol %r is already registered with this transport" % (symbol,)
            )
        self._subscriptions[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol: str) -> None:
        self._subscriptions.pop(symbol, None)

    def close(self) -> None:
        self._subscriptions.clear()

    # ------------------------------------------------------------------
    # operator socket-pump seam
    # ------------------------------------------------------------------

    def notify_down(self, symbol: str | None = None) -> None:
        """Signal stream drop(s): fan out ``on_down`` to every registered
        handler (or exactly one symbol) so workers enter RECONNECTING,
        then tear down the affected registrations.

        Tearing down is part of the drop semantics: the subscription no
        longer exists, exactly like the socket that died.  The worker's
        scheduled reconnect retry re-subscribes through ``subscribe``
        (raising on failure, retried by the worker) and restores LIVE
        delivery.  Frames arriving while a symbol is torn down are
        counted ``unrouted`` -- fail-closed, never queued, never
        delivered late.  Stream state (finality/continuity) is retained:
        a disconnect that spans candle boundaries surfaces as a real
        continuity gap, which blocks closes until repaired or until the
        session restarts.
        """
        if symbol is None:
            targets = list(self._subscriptions.items())
        else:
            registered = self._subscriptions.get(symbol)
            targets = (
                [(symbol, registered)] if registered is not None else []
            )
        for _registered, (_on_candle, on_down) in targets:
            on_down()
        for notified, _handlers in targets:
            self._subscriptions.pop(notified, None)

    def ingest(self, frame: Any, *, receipt_timestamp: Any) -> dict[str, Any]:
        """Feed one raw public frame through the verified chain.

        Returns the stream's ingest record fields for observability; the
        fail-closed delivery decision itself is recorded in ``stats()``.
        """
        result = self._stream.ingest(frame, receipt_timestamp=receipt_timestamp)
        self._frames_ingested += 1

        if result.status != "APPLIED":
            # duplicate / rejected / unhandled frames never deliver.
            self._record_stream_result(result)
            return self._result_record(result)

        closed = result.closed_candle
        if closed is None:
            self._deliver_forming_tick(frame, receipt_timestamp)
            return self._result_record(result)

        decision = to_runtime_candle(
            result, expected_resolution=self._resolution,
        )
        if decision.candle is None:
            # fail-closed: an unverified candle is never delivered.
            self._rejections[decision.reason] += 1
            return self._result_record(result)

        candle = decision.candle
        subscription = self._subscriptions.get(candle.symbol)
        if subscription is None:
            self._unrouted += 1
            return self._result_record(result)

        subscription[0](candle)
        self._closed_delivered += 1
        return self._result_record(result)

    def repair_gap_history(
        self, symbol: str, resolution: str, candles, *,
        receipt_timestamp: int, venue: str | None = None,
    ) -> dict:
        """Operator gap repair through the delivered stream repair path.

        Delegates to ``DeltaPublicEventStream.repair_historical_candles``:
        only candle starts inside an OUTSTANDING gap are accepted (every
        other candidate is rejected and counted), repaired candles are
        appended to the normalized event journal, and continuity state is
        restored so the next live close can deliver again.  Repaired
        candles are deliberately NOT routed through causal finality or
        strategy dispatch: a backfill restores continuity, it does not
        create retroactive live signals.
        """
        return self._stream.repair_historical_candles(
            symbol, resolution, candles,
            receipt_timestamp=receipt_timestamp, venue=venue,
        )

    def continuity_status(self, symbol: str, resolution: str | None = None) -> dict:
        """Observable continuity state for one symbol (fail-closed view).

        ``status`` is ``CONTINUOUS`` or ``DATA_GAP_UNREPAIRED``; a
        ``DATA_GAP_UNREPAIRED`` state is exactly why closes stop being
        delivered (``to_runtime_candle`` refuses them).  An unknown
        symbol/resolution reports ``UNKNOWN`` (nothing tracked yet).
        """
        resolution = resolution or self._resolution
        try:
            return dict(self._stream.continuity.status(
                self._stream.venue, symbol, resolution,
            ))
        except Exception:
            return {
                "status": "UNKNOWN", "gaps": [], "missing_candles": 0,
            }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _deliver_forming_tick(self, frame: Any, receipt_timestamp: Any) -> None:
        """Freshness-only delivery for a forming candlestick frame.

        Values are taken verbatim from the raw frame (nothing fabricated);
        the tick is tagged ``closed=False`` and therefore never reaches
        strategy logic (the 6D worker router drops forming ticks).
        """
        if not isinstance(frame, dict):
            self._rejections["forming frame is not a mapping"] += 1
            return
        channel = frame.get("type")
        if not (
            isinstance(channel, str) and channel.startswith("candlestick_")
        ):
            # applied non-candle event (e.g. trade): nothing to deliver.
            return
        try:
            norm = normalize_candlestick_frame(
                frame, receipt_timestamp=receipt_timestamp,
            )
        except InvalidMarketFrame as error:
            self._rejections[str(error)] += 1
            return
        symbol = norm.provenance.instrument
        subscription = self._subscriptions.get(symbol)
        if subscription is None:
            self._unrouted += 1
            return
        if norm.candle_start_timestamp is None:
            self._rejections[
                "forming candle start timestamp is unavailable"
            ] += 1
            return
        forming = Candle(
            timestamp=norm.candle_start_timestamp,
            open=norm.open,
            high=norm.high,
            low=norm.low,
            close=norm.close,
            volume=norm.volume,
            closed=False,
            symbol=symbol,
        )
        subscription[0](forming)
        self._forming_delivered += 1

    def _record_stream_result(self, result: Any) -> None:
        # reason observability for rejected frames
        if result.status == "REJECTED" and result.reason:
            self._rejections["stream: %s" % (result.reason,)] += 1

    def _result_record(self, result: Any) -> dict[str, Any]:
        return {
            "ingest_status": result.status,
            "ingest_event_type": result.event_type,
            "ingest_reason": result.reason,
        }

    # ------------------------------------------------------------------
    # observability
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "resolution": self._resolution,
            "symbols": tuple(sorted(self._subscriptions)),
            "frames_ingested": self._frames_ingested,
            "forming_delivered": self._forming_delivered,
            "closed_delivered": self._closed_delivered,
            "unrouted": self._unrouted,
            "runtime_rejections": dict(self._rejections),
            "stream": self._stream.stats(),
        }


def verified_public_candle_transport_factory(resolution: str = "1m"):
    """Factory shaped for ``build_paper_engine(transport_factory=...)``."""

    def _factory() -> VerifiedPublicCandleTransport:
        return VerifiedPublicCandleTransport(resolution=resolution)

    return _factory
