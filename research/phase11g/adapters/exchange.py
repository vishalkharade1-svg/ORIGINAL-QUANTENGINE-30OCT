"""11G-E exchange-adapter architecture (research depends on interfaces).

HistoricalDataAdapter is the ONLY exchange surface research may touch.
Exchange URLs live here — never scattered through research code.
No network I/O happens at import; adapters fetch only on explicit call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

DELTA_PUBLIC_BASE = "https://api.delta.exchange"
DELTA_CANDLES_PATH = "/v2/history/candles"
DELTA_WS_PUBLIC = "wss://public-socket.delta.exchange"


class HistoricalDataAdapter(ABC):
    name = "base"

    @abstractmethod
    def candles(self, symbol, resolution, start, end):
        raise NotImplementedError

    def trades(self, symbol, start, end):  # pragma: no cover
        raise NotImplementedError("adapter has no historical trades endpoint")

    def quotes(self, symbol, start, end):  # pragma: no cover
        raise NotImplementedError("adapter has no historical quotes endpoint")

    def book(self, symbol, start, end):  # pragma: no cover
        raise NotImplementedError("adapter has no historical book endpoint")


class DeltaPublicCandlesAdapter(HistoricalDataAdapter):
    """Delta public 1m+ candles (the sole verified historical feed)."""

    name = "delta-public-candles"
    base_url = DELTA_PUBLIC_BASE
    candles_path = DELTA_CANDLES_PATH

    def __init__(self, client=None):
        self._client = client

    def candles(self, symbol, resolution, start, end):
        if self._client is None:
            raise RuntimeError("no HTTP client injected (tests inject fakes)")
        return self._client.get(
            self.base_url + self.candles_path,
            params={"symbol": symbol, "resolution": resolution,
                    "start": start, "end": end})


class AdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, adapter):
        self._adapters[adapter.name] = adapter

    def get(self, name):
        return self._adapters[name]

    def names(self):
        return sorted(self._adapters)
