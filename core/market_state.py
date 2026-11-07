from dataclasses import dataclass, field
from threading import Lock


@dataclass(slots=True)
class MarketState:
    """
    Holds the current market state for replay,
    paper trading and live trading.
    """

    # -------------------------------------------------
    # Identity
    # -------------------------------------------------

    symbol: str = ""

    timeframe: str = "1m"

    # Phase 6C: canonical market scope. exchange + instrument_id
    # name the instrument in the discovery/universe registry and
    # feed the canonical setup identity; empty in legacy
    # single-symbol harnesses that only set symbol.
    exchange: str = ""

    instrument_id: str = ""

    # -------------------------------------------------
    # Prices
    # -------------------------------------------------

    mark_price: float = 0.0

    best_bid: float = 0.0

    best_ask: float = 0.0

    spread: float = 0.0

    # -------------------------------------------------
    # Time
    # -------------------------------------------------

    timestamp: int = 0

    # -------------------------------------------------
    # Connection
    # -------------------------------------------------

    connected: bool = False

    # -------------------------------------------------
    # Synchronization
    # -------------------------------------------------

    lock: Lock = field(default_factory=Lock)