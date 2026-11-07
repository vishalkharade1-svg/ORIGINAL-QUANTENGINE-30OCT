"""Unit tests for MultiStreamMultiplexer (Phase 163)."""

from __future__ import annotations

import unittest
from core.runtime.multi_stream_multiplexer import (
    MultiStreamMultiplexer,
    MultiplexerCandle,
    StreamHealth,
)


class TestMultiStreamMultiplexer(unittest.TestCase):
    def setUp(self):
        self.symbols = ["BTCUSD", "ETHUSD", "SOLUSD"]
        self.mux = MultiStreamMultiplexer(
            self.symbols,
            interval_ms=60000,
            max_candles_per_symbol=5,
            max_unhealthy_symbols_tolerated=1,
        )

    def test_symbols_initialization_and_sorting(self):
        self.assertEqual(self.mux.symbols, ["BTCUSD", "ETHUSD", "SOLUSD"])
        self.assertFalse(self.mux.is_portfolio_halted)

    def test_candle_ingestion_and_isolated_storage(self):
        c_btc = MultiplexerCandle(
            symbol="BTCUSD",
            timestamp_ms=1700000000000,
            open=80000.0,
            high=80100.0,
            low=79950.0,
            close=80050.0,
            volume=1.5,
            is_final=True,
        )
        c_eth = MultiplexerCandle(
            symbol="ETHUSD",
            timestamp_ms=1700000000000,
            open=2500.0,
            high=2510.0,
            low=2490.0,
            close=2505.0,
            volume=10.0,
            is_final=True,
        )

        self.assertTrue(self.mux.ingest_candle(c_btc))
        self.assertTrue(self.mux.ingest_candle(c_eth))

        btc_candles = self.mux.get_candles("BTCUSD")
        eth_candles = self.mux.get_candles("ETHUSD")
        sol_candles = self.mux.get_candles("SOLUSD")

        self.assertEqual(len(btc_candles), 1)
        self.assertEqual(len(eth_candles), 1)
        self.assertEqual(len(sol_candles), 0)
        self.assertEqual(btc_candles[0].close, 80050.0)
        self.assertEqual(eth_candles[0].close, 2505.0)

    def test_symbol_metadata_strict_isolation(self):
        self.mux.set_symbol_metadata("BTCUSD", "trend_regime", "BULLISH_SWING")
        self.mux.set_symbol_metadata("ETHUSD", "trend_regime", "BEARISH_DISPLACEMENT")

        self.assertEqual(self.mux.get_symbol_metadata("BTCUSD", "trend_regime"), "BULLISH_SWING")
        self.assertEqual(self.mux.get_symbol_metadata("ETHUSD", "trend_regime"), "BEARISH_DISPLACEMENT")
        self.assertIsNone(self.mux.get_symbol_metadata("SOLUSD", "trend_regime"))

    def test_unfinalized_candle_rejection(self):
        unfinalized = MultiplexerCandle(
            symbol="BTCUSD",
            timestamp_ms=1700000000000,
            open=80000.0,
            high=80100.0,
            low=79950.0,
            close=80050.0,
            volume=1.5,
            is_final=False,  # Forming candle
        )
        with self.assertRaises(ValueError):
            self.mux.ingest_candle(unfinalized)

    def test_gap_detection_halts_symbol(self):
        t0 = 1700000000000
        c1 = MultiplexerCandle("BTCUSD", t0, 80000.0, 80100.0, 79900.0, 80050.0, 1.0)
        self.assertTrue(self.mux.ingest_candle(c1))

        # Next candle is 180,000 ms later (2 missing 60s bars)
        c2 = MultiplexerCandle("BTCUSD", t0 + 180000, 80050.0, 80200.0, 80000.0, 80150.0, 1.0)
        accepted = self.mux.ingest_candle(c2)
        self.assertFalse(accepted)
        self.assertEqual(self.mux.get_symbol_health("BTCUSD"), StreamHealth.GAPPED)

        # ETHUSD remains healthy and unaffected
        c_eth = MultiplexerCandle("ETHUSD", t0, 2500.0, 2510.0, 2490.0, 2505.0, 5.0)
        self.assertTrue(self.mux.ingest_candle(c_eth))
        self.assertEqual(self.mux.get_symbol_health("ETHUSD"), StreamHealth.HEALTHY)

    def test_portfolio_halt_when_unhealthy_tolerance_exceeded(self):
        t0 = 1700000000000
        # Ingest first bar for BTC and ETH
        self.mux.ingest_candle(MultiplexerCandle("BTCUSD", t0, 80000.0, 80100.0, 79900.0, 80050.0, 1.0))
        self.mux.ingest_candle(MultiplexerCandle("ETHUSD", t0, 2500.0, 2510.0, 2490.0, 2505.0, 5.0))

        # First failure: BTC gaps (tolerance is 1, so portfolio stays active)
        self.mux.ingest_candle(MultiplexerCandle("BTCUSD", t0 + 180000, 80050.0, 80200.0, 80000.0, 80150.0, 1.0))
        self.assertEqual(self.mux.get_symbol_health("BTCUSD"), StreamHealth.GAPPED)
        self.assertFalse(self.mux.is_portfolio_halted)

        # Second failure: ETH gaps (now 2 unhealthy > tolerance of 1 -> triggers portfolio halt)
        self.mux.ingest_candle(MultiplexerCandle("ETHUSD", t0 + 180000, 2505.0, 2520.0, 2500.0, 2515.0, 5.0))
        self.assertEqual(self.mux.get_symbol_health("ETHUSD"), StreamHealth.GAPPED)
        self.assertTrue(self.mux.is_portfolio_halted)
        self.assertIn("Unhealthy streams (2", self.mux.portfolio_halt_reason)

    def test_buffer_sliding_window_cap(self):
        t0 = 1700000000000
        for i in range(10):
            c = MultiplexerCandle(
                "SOLUSD",
                t0 + (i * 60000),
                150.0 + i,
                151.0 + i,
                149.0 + i,
                150.5 + i,
                100.0,
            )
            self.mux.ingest_candle(c)

        candles = self.mux.get_candles("SOLUSD")
        self.assertEqual(len(candles), 5)  # Capped at max_candles_per_symbol=5
        self.assertEqual(candles[-1].close, 159.5)


if __name__ == "__main__":
    unittest.main()
