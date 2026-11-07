"""
====================================================

QuantEngine

Delta History Provider (Phase 9P-d)

A real, provider-backed implementation of the UniverseManager
history duck-contract:

    provider.history_bars(symbol, timeframe) -> int | None

The eligibility cascade (Phase 6B) consumes exactly one history
figure: the COUNT of bars available for an instrument in the
trade timeframe. Existing history modules download actual
Candle data (DeltaHistory / HistoricalLoader / HistoryDatabase)
but none expose the bar-count input the UniverseManager asks
for. This provider is that missing plumbing: it asks the real
Delta /v2/history/candles endpoint (through the existing
DeltaHistory adapter) for the lookback window and reports how
many bars came back.

Data honesty rules (no fabricated eligibility):

  * a symbol with NO history returns None -> DENY
    (NO_HISTORY_DATA), never "assume sufficient history";
  * a transport / parse failure returns None for that symbol
    (the gate denies; the universe loop never dies);
  * the returned count is a LOWER BOUND on available history:
    it is the number of bars actually received for the
    configured lookback window. If that falls below the policy
    threshold the cascade correctly denies. A count that
    exactly equals the fetched window is never treated as
    "more than enough" -- it is simply the measured count.

The history client is injectable so offline tests drive the
exact same code with a fake that returns a controlled bar
count and zero network.

====================================================
"""

from core.exchanges.delta.delta_history import DeltaHistory

DEFAULT_LOOKBACK_DAYS = 7


class DeltaHistoryProvider:
    """Real Delta-backed HistoryProvider (duck-typed).

    history_bars(symbol, timeframe) -> the count of bars
    available in the lookback window, or None when the
    instrument has no measurable history for that timeframe.
    """

    def __init__(self, history=None, lookback_days=DEFAULT_LOOKBACK_DAYS):
        # `history`: anything with .candles(symbol, resolution,
        #   days=...) -> list[Candle]; defaults to the real
        #   DeltaHistory. Injected by tests to script a count.
        self.history = history if history is not None else DeltaHistory()
        self.lookback_days = lookback_days
        self.errors = []

    # -------------------------------------------------

    def history_bars(self, symbol, timeframe="1m"):
        """Count how many bars are available for `symbol` in the
        configured lookback window at `timeframe`.

        Returns an int >= 0 on a successful measurement, or
        None when the exchange could not be measured for this
        symbol (transport error / parse error). None -> the
        cascade DENIES with NO_HISTORY_DATA.
        """
        try:
            candles = self.history.candles(
                symbol,
                resolution=timeframe,
                days=self.lookback_days,
            )
        except Exception as error:
            self.errors.append((symbol, type(error).__name__, str(error)))
            return None

        if candles is None:
            return None
        return len(candles)
