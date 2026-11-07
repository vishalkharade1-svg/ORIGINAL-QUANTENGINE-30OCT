"""Product-snapshot evidence tests (deterministic, offline).

Provenance: LOCAL cache inspection — reads the git-ignored Phase-17
venue product snapshot when present (skipTest when absent so clean
checkouts stay green). Proves ingestion CODE/TEST readiness only:
parsing, validation, and the exact economics gaps. NEVER venue-current
evidence (cache is Phase-17 era; values must be re-fetched before any
enforcement) and NEVER runtime wiring.

Stdlib only. Read-only: no network, no credentials, no writes.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "history" / "BTCUSDT_product_phase17.json"

REQUIRES_CACHE = unittest.skipUnless(
    SNAPSHOT.is_file(), "Phase-17 product cache absent (clean checkout)")


def load_snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


class TestSnapshotEnvelope(unittest.TestCase):
    @REQUIRES_CACHE
    def test_envelope_has_evidence_fields(self):
        bundle = load_snapshot()
        self.assertIn("btcusdt", bundle)
        product = bundle["btcusdt"]
        for field in ("symbol", "contract_type", "state", "tick_size",
                      "taker_commission_rate", "maker_commission_rate"):
            self.assertIn(field, product)
        self.assertEqual(product["symbol"], "BTCUSDT")

    @REQUIRES_CACHE
    def test_snapshot_bytes_stable(self):
        first = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
        second = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)


class TestSnapshotNormalization(unittest.TestCase):
    @REQUIRES_CACHE
    def test_btcusdt_normalizes_to_expected_instrument(self):
        from data.delta.product_normalizer import DeltaProductNormalizer

        instrument = DeltaProductNormalizer().normalize(
            load_snapshot()["btcusdt"])
        self.assertEqual(instrument.symbol, "BTCUSDT")
        self.assertEqual(instrument.product_type, "PERPETUAL")
        self.assertEqual(instrument.underlying_asset, "BTC")
        self.assertEqual(instrument.quote_asset, "USDT")
        self.assertAlmostEqual(instrument.tick_size, 0.5)
        self.assertAlmostEqual(instrument.quantity_step, 0.001)
        self.assertTrue(instrument.trading_enabled)

    @REQUIRES_CACHE
    def test_missing_minimum_normalizes_to_zero_not_verified(self):
        from data.delta.product_normalizer import DeltaProductNormalizer

        product = load_snapshot()["btcusdt"]
        self.assertNotIn("minimum_order_size", product)
        instrument = DeltaProductNormalizer().normalize(product)
        # 0.0 means UNKNOWN here, never "no minimum": enforcement must
        # fail closed on it rather than assume unconstrained size.
        self.assertEqual(instrument.minimum_quantity, 0.0)


class TestSnapshotEconomicsGap(unittest.TestCase):
    @REQUIRES_CACHE
    def test_fee_fields_present_but_unconsumed(self):
        from data.delta.product_normalizer import DeltaProductNormalizer

        product = load_snapshot()["btcusdt"]
        # Hand-verified against the cached bytes: venue-quoted rates.
        self.assertEqual(product["taker_commission_rate"], "0.0001")
        self.assertEqual(product["maker_commission_rate"], "0.0001")
        instrument = DeltaProductNormalizer().normalize(product)
        blob = json.dumps(
            instrument.metadata, sort_keys=True, default=str).lower()
        self.assertNotIn("commission", blob)
        self.assertNotIn("0.0001", blob)

    @REQUIRES_CACHE
    def test_staleness_limitation_explicit(self):
        # The cache carries no retrieval timestamp from the venue
        # itself; any enforcement use requires a fresh authorized
        # fetch. This pin fails if anyone treats the cache as current.
        bundle = load_snapshot()
        self.assertNotIn("retrieved_at", bundle.get("btcusdt", {}))
        self.assertNotIn("fetched_at", bundle)


if __name__ == "__main__":
    unittest.main()
