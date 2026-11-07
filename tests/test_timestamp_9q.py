"""
Phase 9Q-6 — Canonical timestamp normalization.

Tests required:
- seconds, milliseconds, microseconds, nanoseconds
- invalid, None, timezone consistency, boundary values
- All equivalent timestamps normalize to same instant
"""

import unittest

from core.common.timestamp import normalize_timestamp, normalize_timestamp_or_none


class TestTimestampNormalization(unittest.TestCase):

    def test_seconds(self):
        # 2024-01-01 00:00:00 UTC = 1704067200
        self.assertEqual(normalize_timestamp(1704067200), 1704067200)
        self.assertEqual(normalize_timestamp(1704067200.0), 1704067200)
        self.assertEqual(normalize_timestamp("1704067200"), 1704067200)

    def test_milliseconds(self):
        # 1704067200 *1000 = 1704067200000
        self.assertEqual(normalize_timestamp(1704067200000), 1704067200)
        self.assertEqual(normalize_timestamp(1704067200123), 1704067200)
        self.assertEqual(normalize_timestamp("1704067200000"), 1704067200)

    def test_microseconds(self):
        # 1704067200 *1_000_000 = 1704067200000000
        self.assertEqual(normalize_timestamp(1704067200000000), 1704067200)
        self.assertEqual(normalize_timestamp(1704067200123456), 1704067200)

    def test_nanoseconds(self):
        # 1704067200 *1_000_000_000 = 1704067200000000000
        self.assertEqual(normalize_timestamp(1704067200000000000), 1704067200)
        self.assertEqual(normalize_timestamp(1704067200123456789), 1704067200)

    def test_all_equivalent_normalize_to_same(self):
        sec = 1704067200
        ms = 1704067200000
        us = 1704067200000000
        ns = 1704067200000000000
        self.assertEqual(normalize_timestamp(sec), normalize_timestamp(ms))
        self.assertEqual(normalize_timestamp(ms), normalize_timestamp(us))
        self.assertEqual(normalize_timestamp(us), normalize_timestamp(ns))

    def test_invalid_none(self):
        with self.assertRaises(ValueError):
            normalize_timestamp(None)
        self.assertIsNone(normalize_timestamp_or_none(None))

    def test_invalid_string_empty(self):
        with self.assertRaises(ValueError):
            normalize_timestamp("")
        with self.assertRaises(ValueError):
            normalize_timestamp("   ")
        with self.assertRaises(ValueError):
            normalize_timestamp("abc")

    def test_invalid_zero_negative(self):
        with self.assertRaises(ValueError):
            normalize_timestamp(0)
        with self.assertRaises(ValueError):
            normalize_timestamp(-100)
        with self.assertRaises(ValueError):
            normalize_timestamp(-1704067200000)

    def test_invalid_non_numeric(self):
        with self.assertRaises(ValueError):
            normalize_timestamp({})
        with self.assertRaises(ValueError):
            normalize_timestamp([])

    def test_boundary_values(self):
        # Just below 1e12 should be seconds (e.g., 999_999_999_999 is year 33658 if seconds, but treat as seconds)
        # Our threshold is 1e12 for ms, so 999_999_999_999 is still seconds per our logic
        # But 1_000_000_000_000 is ms threshold
        self.assertEqual(normalize_timestamp(1_000_000_000_000), 1_000_000_000)  # 1e12 ms -> 1e9 sec
        self.assertEqual(normalize_timestamp(999_999_999_999), 999_999_999_999)  # still seconds (large but <1e12)
        # µs threshold
        self.assertEqual(normalize_timestamp(1_000_000_000_000_000), 1_000_000_000)  # 1e15 µs -> 1e9
        # ns threshold
        self.assertEqual(normalize_timestamp(1_000_000_000_000_000_000), 1_000_000_000)  # 1e18 ns -> 1e9

    def test_timezone_consistency(self):
        # Canonical is UTC seconds, so same instant in different representations must match
        # Simulate exchange sending ms vs us for same instant
        instant_sec = 1704067200
        self.assertEqual(normalize_timestamp(instant_sec * 1000), instant_sec)
        self.assertEqual(normalize_timestamp(instant_sec * 1_000_000), instant_sec)
        self.assertEqual(normalize_timestamp(instant_sec * 1_000_000_000), instant_sec)

    def test_float_seconds_with_fraction(self):
        self.assertEqual(normalize_timestamp(1704067200.999), 1704067200)
        self.assertEqual(normalize_timestamp(1704067200.123), 1704067200)

    def test_or_none_returns_none_on_invalid(self):
        self.assertIsNone(normalize_timestamp_or_none(None))
        self.assertIsNone(normalize_timestamp_or_none(0))
        self.assertIsNone(normalize_timestamp_or_none("bad"))

    def test_candle_builder_accepts_all_units(self):
        from data.candle_builder import CandleBuilder
        builder = CandleBuilder(timeframe="1m")
        # Same instant in different units should bucket identically
        sec = 1704067200  # 2024-01-01 00:00:00
        # First tick at 00:00:00 in seconds
        b1 = builder.update(sec, 100.0)
        self.assertIsNone(b1)  # first tick creates current, no finished
        # Second tick same bucket should update same candle, not finish
        b2 = builder.update(sec + 10, 101.0)
        self.assertIsNone(b2)
        # Next bucket: 00:01:00
        b3 = builder.update(sec + 60, 102.0)
        self.assertIsNotNone(b3)
        self.assertEqual(b3.timestamp, sec - (sec % 60))

        # Now test ms/µs/ns equivalence
        builder2 = CandleBuilder(timeframe="1m")
        builder2.update(sec * 1000, 100.0)  # ms
        builder2.update((sec + 10) * 1000, 101.0)
        fin = builder2.update((sec + 60) * 1000, 102.0)
        self.assertIsNotNone(fin)
        self.assertEqual(fin.timestamp, sec - (sec % 60))

        builder3 = CandleBuilder(timeframe="1m")
        builder3.update(sec * 1_000_000, 100.0)  # µs
        builder3.update((sec + 10) * 1_000_000, 101.0)
        fin3 = builder3.update((sec + 60) * 1_000_000, 102.0)
        self.assertIsNotNone(fin3)
        self.assertEqual(fin3.timestamp, sec - (sec % 60))
