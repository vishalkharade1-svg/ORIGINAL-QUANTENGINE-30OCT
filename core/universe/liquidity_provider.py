"""
====================================================

QuantEngine

Delta Liquidity Provider (Phase 9P-d)

A real, provider-backed implementation of the UniverseManager
liquidity duck-contract:

    provider.quote_volume_24h(symbol) -> float | None

The eligibility cascade (Phase 6B) consumes exactly one
liquidity figure: the 24h QUOTE VOLUME in USD. None of the
existing modules produced one -- the products catalog
(/v2/products) carries no volume field, and the live ticker
WebSocket path extracts only mark/bid/ask. This provider is
the missing plumbing: it fetches the real Delta /v2/tickers
payload and maps each symbol's `turnover_usd` (24h USD
turnover, verified against the live API) to the canonical
quote_volume_24h input.

Data honesty rules (no fabricated eligibility):

  * a symbol with MISSING / empty / unparseable turnover
    returns None  -> the cascade DENIES (NO_LIQUIDITY_DATA),
    never "assume liquid" on missing data;
  * a transport failure on one symbol returns None for that
    symbol (the loop never dies; the gate still denies);
  * zero turnover returns None -- a literally un-liquidity'd
    product cannot be traded as if it had volume.

The full ticker list is fetched once per refresh and cached
as a symbol -> turnover map, so a multi-symbol eligibility
pass is ONE REST call, not one per instrument. Everything is
injectable so offline tests drive the exact same code with a
mocked transport and zero network.

====================================================
"""

from core.exchanges.delta.delta_rest import DeltaREST

TICKERS_ENDPOINT = "/v2/tickers"


def _to_float_or_none(value):
    """Coerce a Delta turnover field to a positive float, or
    None when it is missing / empty / garbage / non-positive.

    Delta returns turnover_usd as a string for the liquid
    set ("3083174.2395") and as an empty string "" for
    inactive products. Missing or non-positive is a
    "cannot measure" -> None, which the eligibility cascade
    treats as a DENY (NO_LIQUIDITY_DATA).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0.0:
        return None
    return number


class DeltaLiquidityProvider:
    """Real Delta-backed LiquidityProvider (duck-typed).

    quote_volume_24h(symbol) -> a positive float (USD 24h
    turnover) for a measurable product, or None when the
    product has no / unmeasurable 24h turnover.
    """

    def __init__(self, transport=None, fetch=None):
        # `transport`: anything with .get(endpoint, params=None),
        # like DeltaREST or an offline mock.
        self.rest = transport if transport is not None else DeltaREST()
        # `fetch`: optional override returning the raw tickers
        # payload dict ({"result": [...]}). Injected by tests to
        # script responses without a transport layer.
        self._fetch = fetch
        # symbol -> float | None (last refresh's snapshot)
        self._turnover_by_symbol = {}
        self.fetch_count = 0

    # -------------------------------------------------

    def refresh(self):
        """Fetch the current /v2/tickers snapshot once.

        Returns True on a successful fetch (even an empty
        one); False when the transport itself raised, so a
        caller can surface a degraded refresh without the
        universe loop dying. A failed refresh leaves the
        previous snapshot in place -- a stale-but-present
        measurement is still a measurement; an absent symbol
        resolves to None and is denied.
        """
        self.fetch_count += 1
        try:
            payload = (
                self._fetch()
                if self._fetch is not None
                else self.rest.get(TICKERS_ENDPOINT)
            )
        except Exception:
            return False

        if isinstance(payload, dict):
            rows = payload.get("result") or []
        else:
            rows = payload or []

        snapshot = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if not symbol:
                continue
            snapshot[symbol] = _to_float_or_none(
                row.get("turnover_usd")
            )
        self._turnover_by_symbol = snapshot
        return True

    # -------------------------------------------------

    def quote_volume_24h(self, symbol):
        """The canonical liquidity input for one instrument.

        Returns the latest measured 24h USD turnover, or None
        when the symbol is absent from the snapshot (no data
        -> deny, never assume liquid).
        """
        return self._turnover_by_symbol.get(symbol)
