"""Delta MCP public evidence: fixture contract + gate evaluation.

Stdlib-only. Pins the MCP-bridged external evidence without
weakening any authority:

* the MCP observation fixture is keyless, testnet-scoped, and
  carries no credential-shaped material;
* observed venue fields are present verbatim; absent venue fields
  are listed as unavailable (never defaulted);
* DeltaMapper comparison pins both the matched fields and the
  reported default discrepancies (mapper untouched);
* G4/G5 evaluate to PARTIAL through the real evaluator helpers;
* the resulting matrix passes validate_matrix with the external
  aggregate honestly BLOCKED (G2 still REJECTED).
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (REPO_ROOT / "data" / "fixtures" / "delta"
           / "delta_mcp_public_products_20260925.json")

FORBIDDEN_KEYS = {"api_key", "api_secret", "secret", "password",
                  "token", "authorization", "signature", "private_key",
                  "access_token", "refresh_token"}


def _load_evaluator():
    path = REPO_ROOT / "scripts" / "evaluate_evidence_gates.py"
    spec = importlib.util.spec_from_file_location(
        "evidence_gate_evaluator", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan(node, keys, strings):
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                keys.append(key)
            _scan(value, keys, strings)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _scan(value, keys, strings)
    elif isinstance(node, str) and node:
        strings.append(node)


class TestMcpFixtureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_envelope(self):
        self.assertEqual(
            self.body["schema"], "quantengine.mcp-public-observation.v1")
        self.assertEqual(self.body["observed_date"], "2026-09-25")

    def test_keyless_testnet_provenance(self):
        provenance = self.body["provenance"]
        self.assertEqual(provenance["delta_mcp_env"], "india_testnet")
        self.assertFalse(provenance["credentials_configured"])
        self.assertFalse(provenance["account_tools_available"])
        self.assertFalse(provenance["trading_tools_available"])
        self.assertIn("get_product", provenance["tools_used"])
        connection = self.body["connection_status"]
        self.assertEqual(connection["environment"], "india_testnet")

    def test_no_credential_material(self):
        keys, _ = [], []
        found_keys, found_strings = [], []
        _scan(self.body, found_keys, found_strings)
        self.assertEqual(found_keys, [])

    def test_product_observed_verbatim(self):
        (product,) = self.body["products"]
        self.assertEqual(product["symbol"], "BTCUSD")
        self.assertEqual(product["contract_type"], "perpetual_futures")
        self.assertEqual(product["state"], "live")
        self.assertEqual(product["tick_size"], "0.1")
        self.assertEqual(product["contract_value"], "0.001")
        self.assertEqual(product["maker_commission_rate"], "0.0002")
        self.assertEqual(product["taker_commission_rate"], "0.0005")
        self.assertEqual(product["underlying_asset"]["symbol"], "BTC")
        self.assertEqual(product["quoting_asset"]["symbol"], "USD")
        self.assertEqual(product["settling_asset"]["symbol"], "USD")

    def test_gaps_listed_not_defaulted(self):
        unavailable = self.body["unavailable"]
        for gap in ("minimum_order_size", "price_precision",
                    "maximum_leverage", "full product catalog"):
            self.assertTrue(
                any(gap in item for item in unavailable), gap)


class TestMapperComparison(unittest.TestCase):
    def test_matched_and_defaulted_fields(self):
        from core.exchanges.delta.delta_mapper import DeltaMapper

        body = json.loads(FIXTURE.read_text(encoding="utf-8"))
        (product,) = body["products"]
        mapped = DeltaMapper().map(product)
        # Observed fields flow through the existing authority.
        self.assertEqual(mapped.symbol, "BTCUSD")
        self.assertEqual(mapped.tick_size, 0.1)
        self.assertEqual(mapped.product_id, 84)
        self.assertAlmostEqual(mapped.maker_fee, 0.0002)
        self.assertAlmostEqual(mapped.taker_fee, 0.0005)
        self.assertEqual(mapped.underlying_asset, "BTC")
        self.assertEqual(mapped.quantity_step, 0.001)
        # Absent venue fields fall back to mapper defaults --
        # recorded as UNAVAILABLE by the gates, never as observed.
        self.assertEqual(mapped.min_quantity, 0.0)
        self.assertEqual(mapped.max_leverage, 1.0)
        self.assertEqual(mapped.price_precision, 2)
        self.assertEqual(mapped.quantity_precision, 3)


class TestMcpGateEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluator = _load_evaluator()

    def test_g4_partial_public(self):
        result = self.evaluator._mcp_g4_evaluation()
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(result.execution_state, "EXECUTED")
        self.assertNotIn("authenticated_source", result.observed_evidence)
        self.assertTrue(any("BTCUSD" in item
                            for item in result.observed_evidence))
        for gap in ("price_precision", "quantity_precision",
                    "minimum_order_size"):
            self.assertTrue(
                any(gap in item for item in result.missing_evidence),
                gap)

    def test_g5_partial_public(self):
        result = self.evaluator._mcp_g5_evaluation(g4_partial=True)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "PARTIAL")
        self.assertNotIn("contract_identity_required",
                         result.observed_evidence)
        self.assertTrue(any("maker_fee=0.0002" in item
                            for item in result.observed_evidence))
        self.assertTrue(any("taker_fee=0.0005" in item
                            for item in result.observed_evidence))
        self.assertTrue(any("slippage" in item
                            for item in result.missing_evidence))

    def test_g5_without_identity_is_none(self):
        self.assertIsNone(
            self.evaluator._mcp_g5_evaluation(g4_partial=False))

    def test_partial_matrix_validates_blocked_aggregate(self):
        from core.evidence.gates import (
            DEFINITIONS,
            GateResult,
            external_final,
            validate_matrix,
        )

        def _res(gate_id, status="VERIFIED", execution="EXECUTED",
                 **over):
            params = {"gate_id": gate_id, "status": status,
                      "execution_state": execution,
                      "prerequisites": (),
                      "satisfied_prerequisites": (),
                      "missing_prerequisites": (),
                      "required_evidence": (),
                      "observed_evidence": (),
                      "missing_evidence": (),
                      "blocking_reasons": (),
                      "limitations": ()}
            params.update(over)
            return GateResult(**params)

        g4 = self.evaluator._mcp_g4_evaluation()
        g5 = self.evaluator._mcp_g5_evaluation(g4_partial=True)
        by_id = {gid: _res(gid) for gid in
                 ("G0", "G1", "G8", "G9", "G10", "G11", "G12", "G13",
                  "G14")}
        by_id.update({
            "G2": _res("G2", status="BLOCKED",
                       observed_evidence=("exchange_response", "http_401",
                                          "mcp_env=india_testnet"),
                       missing_evidence=("authenticated_response",),
                       blocking_reasons=("AUTHENTICATION_REJECTED",)),
            "G3": _res("G3", status="BLOCKED",
                       execution="BLOCKED_BY_PREREQUISITE",
                       prerequisites=("G2",),
                       missing_prerequisites=("G2",)),
            "G4": g4,
            "G5": g5,
            "G6": _res("G6", status="BLOCKED",
                       execution="BLOCKED_BY_PREREQUISITE",
                       prerequisites=("G2", "G3", "G4"),
                       missing_prerequisites=("G2", "G3", "G4")),
            "G7": _res("G7", status="PARTIAL",
                       observed_evidence=("account=NO_SOURCE",
                                          "contract=PARTIAL",
                                          "economics=PARTIAL",
                                          "lifecycle=NO_SOURCE"),
                       missing_evidence=("account_source",
                                         "lifecycle_source")),
        })
        self.assertEqual(
            validate_matrix(by_id), "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")
        self.assertEqual(
            external_final(by_id), "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")
        self.assertEqual(
            tuple(p.gate_id for p in DEFINITIONS["G6"].prerequisites),
            ("G2", "G3", "G4"))


if __name__ == "__main__":
    unittest.main()
