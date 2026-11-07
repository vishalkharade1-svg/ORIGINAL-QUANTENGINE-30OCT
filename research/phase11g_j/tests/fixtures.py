"""11G-J golden fixtures (hand-computed, SYNTHETIC, tests only).

Ten events, known price/quantity/side/timestamps. Hand-computed:
buy vol = 1.0+2.0+0.5 = 3.5; sell vol = 1.5+3.0 = 4.5; delta = -1.0;
CVD ends at -1.0; minute-bucket footprint levels as asserted.
"""

from research.phase11g_j.replay.events import RealTrade

T0 = 1788566400000

GOLDEN = [
    RealTrade(T0 + 0, T0 * 1000 + 0, 0, "X", "test", 100.00, 1.0, "buy", "g1", "g1", "g1"),
    RealTrade(T0 + 0, T0 * 1000 + 1, 1, "X", "test", 100.01, 2.0, "buy", "g2", "g2", "g2"),
    RealTrade(T0 + 1, T0 * 1000 + 2, 2, "X", "test", 100.02, 1.5, "sell", "g3", "g3", "g3"),
    RealTrade(T0 + 2, T0 * 1000 + 3, 3, "X", "test", 100.00, 0.5, "buy", "g4", "g4", "g4"),
    RealTrade(T0 + 3, T0 * 1000 + 4, 4, "X", "test", 99.99, 3.0, "sell", "g5", "g5", "g5"),
]

GOLDEN_BUY = 3.5
GOLDEN_SELL = 4.5
GOLDEN_DELTA = -1.0
GOLDEN_TOTAL = 8.0
