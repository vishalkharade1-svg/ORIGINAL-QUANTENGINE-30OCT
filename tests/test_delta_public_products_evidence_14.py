"""Phase-14-external: genuine public venue product evidence (offline).

Consumes the credential-free capture
data/fixtures/delta/observed_global_products_public_20260923.json
(PUBLIC /v2/products, no auth, no state change) and proves:

  1. artifact integrity (schema, endpoint, provenance, deterministic
     evidence_id recomputation);
  2. sanitization (no credential/auth material anywhere);
  3. loader/parser ingestion (DeltaMapper maps every listed entry;
     venue-provided fields land verbatim; absent venue fields fall
     back to documented mapper defaults — recorded, not hidden);
  4. NOT_LISTED symbols carry no fabricated terms;
  5. the snapshot can NEVER authorize live execution
     (live_execution_verified defaults False -> the executor's
     evidence gate refuses).

This is PARSER/INGESTION evidence only. It does not provision
sizing, economics, or live authority. Deterministic, stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (ROOT / "data" / "fixtures" / "delta"
            / "observed_global_products_public_20260923.json")

EXPECTED_LISTED = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT",
                   "XRPUSDT"}
EXPECTED_UNLISTED = {"ADAUSDT", "AVAXUSDT", "BNBUSDT", "LINKUSDT",
                     "ZECUSDT"}

FORBIDDEN_TOKENS = ("DELTA_API_KEY", "DELTA_API_SECRET", "api-key",
                    "signature", "Authorization", "Bearer", "token",
                    "secret", "password", "cookie")


def load_artifact() -> dict:
    return json.loads(ARTIFACT.read_bytes().decode("utf-8"))


class TestArtifactIntegrity(unittest.TestCase):
    def test_schema_provenance_and_evidence_id(self):
        art = load_artifact()
        self.assertEqual(
            art["schema"], "quantengine.delta-public-products.v1")
        self.assertEqual(art["endpoint"],
                         "https://api.delta.exchange")
        self.assertIn("none", art["auth"])
        self.assertFalse(art["state_changing"])
        self.assertGreaterEqual(art["catalog_size"], 400)
        # Deterministic evidence ID: recompute over the canonical
        # content (everything except the id itself).
        body = {k: v for k, v in art.items() if k != "evidence_id"}
        recomputed = hashlib.sha256(
            json.dumps(body, sort_keys=True,
                       default=str).encode("utf-8")).hexdigest()
        self.assertEqual(art["evidence_id"], "sha256:" + recomputed)

    def test_sanitized_no_credential_material(self):
        raw = ARTIFACT.read_bytes().decode("utf-8")
        lowered = raw.lower()
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token.lower(), lowered, token)


class TestMapperIngestion(unittest.TestCase):
    def test_listed_entries_map_with_venue_values(self):
        from core.exchanges.delta.delta_mapper import DeltaMapper

        art = load_artifact()
        mapper = DeltaMapper()
        seen = {}
        for symbol in EXPECTED_LISTED:
            record = art["products"][symbol]
            self.assertTrue(record["listed"], symbol)
            contract = mapper.map(record["entry"])
            self.assertEqual(contract.symbol, symbol)
            self.assertEqual(contract.contract_type,
                             "perpetual_futures")
            self.assertGreater(contract.product_id, 0)
            self.assertGreater(contract.tick_size, 0)
            self.assertGreater(contract.quantity_step, 0)
            seen[symbol] = contract
        # Venue-diverse values land verbatim (no normalization to
        # the paper fallback's fictional SPOT/0.01).
        self.assertAlmostEqual(seen["BTCUSDT"].tick_size, 0.5)
        self.assertAlmostEqual(
            seen["BTCUSDT"].quantity_step, 0.001)
        self.assertAlmostEqual(seen["ETHUSDT"].tick_size, 0.05)
        # Venue-provided fee rates land verbatim where present.
        self.assertGreaterEqual(
            seen["BTCUSDT"].taker_fee, 0.0)
        self.assertGreaterEqual(
            seen["SOLUSDT"].taker_fee, 0.0)

    def test_absent_venue_fields_use_documented_defaults(self):
        # The venue does not provide minimum_order_size,
        # maximum_leverage, or precisions on these entries; the
        # mapper's documented defaults apply. Recorded here so the
        # gap stays visible (a production default, not verification).
        from core.exchanges.delta.delta_mapper import DeltaMapper

        art = load_artifact()
        contract = DeltaMapper().map(
            art["products"]["BTCUSDT"]["entry"])
        self.assertEqual(contract.min_quantity, 0.0)
        self.assertEqual(contract.max_leverage, 1.0)
        self.assertEqual(contract.price_precision, 2)
        self.assertEqual(contract.quantity_precision, 3)

    def test_unlisted_carry_no_fabricated_terms(self):
        art = load_artifact()
        for symbol in EXPECTED_UNLISTED:
            record = art["products"][symbol]
            self.assertFalse(record["listed"], symbol)
            self.assertEqual(record["status"], "NOT_LISTED")
            self.assertNotIn("entry", record)

    def test_snapshot_cannot_authorize_live_execution(self):
        # Mapped contracts default live_execution_verified=False,
        # so the executor's evidence gate refuses them. Real
        # metadata is not live authority.
        from core.exchanges.delta.delta_mapper import DeltaMapper
        from core.execution.order_executor import (
            InvalidContractError,
        )

        from core.execution.order_executor import DeltaOrderExecutor

        art = load_artifact()
        contract = DeltaMapper().map(
            art["products"]["BTCUSDT"]["entry"])
        self.assertFalse(contract.live_execution_verified)
        with self.assertRaises(InvalidContractError):
            DeltaOrderExecutor._require_execution_evidence(
                contract, "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
