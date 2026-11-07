"""Unified verified paper/live runtime (Phase 4 local track).

Paper/live parity requires ONE canonical normalized market-data architecture
with execution as the only difference — never PAPER on a new pipeline while
LIVE stays on the legacy EventBus/ticker path.

Both runtimes below share:

* an explicit multi-symbol list (no ``SYMBOLS[0]`` single-symbol limitation),
* one evidence-gated ``VerifiedSocketTransport`` (Global endpoint only,
  per-symbol ``CandleSessionGate``, bridge + dispatch gates),
* the same closed-candle delivery callback shape.

They differ ONLY at the execution sink:

* ``VerifiedPaperRuntime`` → ``PaperFillSink`` (in-memory simulated fills,
  zero exchange writes, every fill tagged with its economics profile).
* ``VerifiedLiveRuntime`` → ``LiveOrderSink`` (routes to a caller-supplied
  executor AND requires an armed live-safety authorization object; without
  it construction raises fail-closed).

Neither runtime imports the legacy ticker transport or the legacy EventBus
feed.  Both stay disconnected (no strategy delivery) until the transport's
Global evidence gate passes AND post-connect resynchronization completes.

Live-safety seam (EXTERNAL VERIFICATION REQUIRED at wiring time): production
must pass the result of ``LiveSafetyGate.require(...)`` as ``safety`` after
confirming its armed attribute mapping.  This module checks
``getattr(safety, "armed", False) is True``; if the real gate exposes arming
under a different shape, the wiring step must adapt this seam with a test —
never bypass it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from core.history.candle import Candle
from data.delta.verified_socket_transport import VerifiedSocketTransport


def default_delta_history_fetcher(symbol: str, resolution: str, after_ts: int, before_ts: int):
    """Return genuine Delta REST candles for one exact live-feed gap.

    Network access is deliberately lazy: constructing a verified runtime never
    performs I/O. The existing DeltaHistory adapter remains the single source
    for public historical candles; no second REST client or synthetic fallback
    is introduced.
    """
    from core.exchanges.delta.delta_history import DeltaHistory

    return DeltaHistory().gap_candles(symbol, resolution, after_ts, before_ts)


class LiveNotAuthorized(RuntimeError):
    """Live execution was requested without armed live-safety authorization."""


class PaperFillSink:
    """In-memory paper execution sink.  Zero exchange writes by construction."""

    def __init__(self, *, economics_profile: str = "explicit-zero-neutral",
                 economics_version: str = "1"):
        self.economics_profile = economics_profile
        self.economics_version = economics_version
        self.delivered: list[Candle] = []
        self.fills: list[dict[str, Any]] = []

    def __call__(self, candle: Candle) -> None:
        self.delivered.append(candle)
        self.fills.append({
            "symbol": candle.symbol,
            "entry": candle.close,
            "quantity": 0.0,
            "simulated": True,
            "economics_profile": self.economics_profile,
            "economics_version": self.economics_version,
        })


class LiveOrderSink:
    """Live execution sink.  Requires armed authorization; routes to executor."""

    def __init__(self, executor: Callable[[Candle], Any], *, safety: Any):
        if not callable(executor):
            raise TypeError("live executor callable is required")
        if getattr(safety, "armed", False) is not True:
            raise LiveNotAuthorized(
                "live sink requires armed live-safety authorization; "
                "unrestricted live orders are never placed")
        self.executor = executor
        self.safety = safety
        self.routed: list[Candle] = []

    def __call__(self, candle: Candle) -> Any:
        self.routed.append(candle)
        return self.executor(candle)


class _VerifiedRuntimeBase:
    resolution: str = "1m"

    def __init__(self, symbols: Iterable[str], sink: Callable[[Candle], None],
                 *, resolution: str = "1m", venue: str = "DELTA_GLOBAL",
                 evidence_bundle: str | None = None,
                 socket_factory: Callable[[str], Any] | None = None,
                 history_fetcher: Callable[[str, str, int, int], Any] | None = None):
        normalized = sorted({s for s in symbols if isinstance(s, str) and s})
        if not normalized:
            raise ValueError("at least one non-empty symbol is required")
        self.symbols = normalized
        self.sink = sink
        if history_fetcher is None:
            history_fetcher = default_delta_history_fetcher
        self.transport = VerifiedSocketTransport(
            normalized, self._on_verified_candle,
            resolution=resolution, venue=venue,
            evidence_bundle=evidence_bundle,
            socket_factory=socket_factory,
            history_fetcher=history_fetcher,
        )

    def _on_verified_candle(self, candle: Candle) -> None:
        self.sink(candle)

    def connect(self, *, timeout: float = 15.0) -> None:
        self.transport.connect(timeout=timeout)

    def close(self) -> None:
        self.transport.close()

    def repair_gaps(self, symbol: str) -> dict[str, Any]:
        return self.transport.repair_gaps(symbol)

    def ingest(self, frame: Any, *, receipt_timestamp: Any) -> dict[str, Any]:
        return self.transport.ingest(frame, receipt_timestamp=receipt_timestamp)

    def stats(self) -> dict[str, Any]:
        return {"symbols": list(self.symbols), "transport": self.transport.stats()}


class VerifiedPaperRuntime(_VerifiedRuntimeBase):
    """Canonical PAPER runtime on the verified architecture (dry, offline)."""

    def __init__(self, symbols: Iterable[str], *,
                 resolution: str = "1m", venue: str = "DELTA_GLOBAL",
                 evidence_bundle: str | None = None,
                 socket_factory: Callable[[str], Any] | None = None,
                 history_fetcher: Callable[[str, str, int, int], Any] | None = None,
                 economics_profile: str = "explicit-zero-neutral",
                 economics_version: str = "1"):
        sink = PaperFillSink(economics_profile=economics_profile,
                             economics_version=economics_version)
        super().__init__(symbols, sink, resolution=resolution, venue=venue,
                         evidence_bundle=evidence_bundle,
                         socket_factory=socket_factory,
                         history_fetcher=history_fetcher)
        self.paper_sink: PaperFillSink = sink


class VerifiedLiveRuntime(_VerifiedRuntimeBase):
    """Canonical LIVE runtime on the verified architecture (gated writes)."""

    def __init__(self, symbols: Iterable[str],
                 executor: Callable[[Candle], Any], *, safety: Any,
                 resolution: str = "1m", venue: str = "DELTA_GLOBAL",
                 evidence_bundle: str | None = None,
                 socket_factory: Callable[[str], Any] | None = None,
                 history_fetcher: Callable[[str, str, int, int], Any] | None = None):
        sink = LiveOrderSink(executor, safety=safety)
        super().__init__(symbols, sink, resolution=resolution, venue=venue,
                         evidence_bundle=evidence_bundle,
                         socket_factory=socket_factory,
                         history_fetcher=history_fetcher)
        self.live_sink: LiveOrderSink = sink
