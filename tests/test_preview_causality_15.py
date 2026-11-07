"""Paper-preview causality (offline, deterministic).

Uses the real-bar offline fixture
(tests/fixtures/real_btcusdt_1m_600.json — genuine captured
BTCUSDT 1m bars, provenance-labeled; deterministic input, NOT
live evidence): proves future market data cannot alter
previously finalized pipeline decisions, and that repeated runs
are identical. No network.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

FIXTURE = (Path(__file__).resolve().parent / "fixtures"
           / "real_btcusdt_1m_600.json")
PREFIX_BARS = 540


def load_bars():
    from core.history.candle import Candle

    data = json.loads(FIXTURE.read_bytes().decode("utf-8"))
    out = []
    for raw in data["bars"]:
        out.append(Candle(timestamp=int(raw["timestamp"]),
                          open=float(raw["open"]),
                          high=float(raw["high"]),
                          low=float(raw["low"]),
                          close=float(raw["close"]),
                          volume=float(raw["volume"]),
                          symbol="BTCUSDT", closed=True))
    return out


def snapshot(context):
    """Deterministic per-bar decision fingerprint."""
    setups = getattr(context, "trade_setups", None) or []
    signal = getattr(context, "execution_signal", None)
    signals = getattr(context, "execution_signals", None) or []
    snap_setups = []
    for setup in setups:
        snap_setups.append((
            str(getattr(setup, "setup_id", "")),
            str(getattr(setup, "direction", "")),
            round(float(getattr(setup, "entry", 0.0) or 0.0), 6),
            round(float(getattr(setup, "stop_loss", 0.0) or 0.0),
                  6),
            round(float(getattr(setup, "take_profit", 0.0) or 0.0),
                  6),
        ))
    snap_setups.sort()
    return {
        "setups": snap_setups,
        "signal": (None if signal is None else (
            str(getattr(signal, "setup_id", "")),
            str(getattr(signal, "direction", "")),
            round(float(getattr(signal, "entry", 0.0) or 0.0),
                  6))),
        "n_signals": len(signals),
    }


def run_incremental(bars):
    from core.pipeline.institutional_pipeline import (
        InstitutionalPipeline,
    )
    from core.pipeline.pipeline_context import PipelineContext

    context = PipelineContext()
    pipeline = InstitutionalPipeline(context)
    snaps = []
    for candle in bars:
        context.add_candle(candle)
        pipeline.process()
        snaps.append(snapshot(context))
    return snaps


class TestPreviewCausality(unittest.TestCase):
    def test_fixture_has_genuine_decisions(self):
        bars = load_bars()
        self.assertEqual(len(bars), 600)
        snaps = run_incremental(bars[:PREFIX_BARS])
        active = sum(1 for snap in snaps if snap["setups"])
        # The prefix must actually exercise decisions, or the
        # lookahead test below would be vacuous.
        self.assertGreater(active, 0)

    def test_future_data_cannot_alter_prior_decisions(self):
        bars = load_bars()
        prefix_snaps = run_incremental(bars[:PREFIX_BARS])
        full_snaps = run_incremental(bars)
        # Prior finalized per-bar decisions are byte-identical
        # whether or not the future 60 bars are later appended.
        self.assertEqual(prefix_snaps, full_snaps[:PREFIX_BARS])

    def test_repeated_runs_identical(self):
        bars = load_bars()
        first = run_incremental(bars)
        second = run_incremental(bars)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
