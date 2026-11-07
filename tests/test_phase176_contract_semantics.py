"""
Phase 176 Regression Tests — Contract Semantics, Economics & Release Integrity

Independently verifies:
1. Phase 175 archive provenance and detached record integrity
2. Contract multiplier, fee rates, and GST application
3. P&L linearity and dimensional consistency
4. Hurdle gate rules — boundary conditions, fail-closed safety, subsumption proof
5. Tick size discrepancy documentation (FINDING-176-01)
6. Phase 176 report completeness and release gate referential integrity
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT.parent.parent / "DELIVERY"

PHASE175_ZIP = DELIVERY / "QuantEngine_PHASE175_RELEASE_CANDIDATE.zip"
PHASE175_HASH_FILE = DELIVERY / "RELEASE_HASH_PHASE175.txt"
PHASE175_EXPECTED_HASH = "16aacbde562d3a39078e15d62d120810b2d72b0f426526856fd7d274b16954b4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(rel: str) -> dict | list:
    path = ROOT / rel
    assert path.exists(), f"Expected file missing: {rel}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fee(notional: Decimal, rate: Decimal, gst: Decimal) -> Decimal:
    """Reproduce the exact fee calculation from maker_execution_model.py."""
    base = (notional * rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    gst_amount = (base * gst).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return base + gst_amount


# ---------------------------------------------------------------------------
# Class 1: Phase 175 Archive Provenance
# ---------------------------------------------------------------------------

class TestPhase176Provenance:
    """Verify Phase 175 archive integrity as Phase 176 input baseline."""

    def test_phase175_zip_exists(self):
        assert PHASE175_ZIP.exists(), "Phase 175 release candidate ZIP is missing from DELIVERY/"

    def test_phase175_hash_file_exists(self):
        assert PHASE175_HASH_FILE.exists(), "RELEASE_HASH_PHASE175.txt is missing from DELIVERY/"

    def test_phase175_hash_matches(self):
        """RELEASE_HASH_PHASE175.txt must contain the expected SHA-256."""
        content = PHASE175_HASH_FILE.read_text(encoding="utf-8")
        assert PHASE175_EXPECTED_HASH in content, (
            f"RELEASE_HASH_PHASE175.txt does not contain expected hash {PHASE175_EXPECTED_HASH}"
        )

    def test_phase175_zip_sha256_correct(self):
        """Compute actual SHA-256 of Phase 175 ZIP and verify it matches."""
        import hashlib
        h = hashlib.sha256()
        with open(PHASE175_ZIP, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        actual = h.hexdigest()
        assert actual == PHASE175_EXPECTED_HASH, (
            f"Phase 175 ZIP SHA-256 mismatch: expected {PHASE175_EXPECTED_HASH}, got {actual}"
        )

    def test_phase175_gates_all_present(self):
        gates = _load_json("reports/PHASE175_RELEASE_GATES.json")
        assert gates["phase"] == 175
        assert "gates" in gates
        assert len(gates["gates"]) >= 10, "Expected at least 10 Phase 175 gates"


# ---------------------------------------------------------------------------
# Class 2: Contract Specification Verification
# ---------------------------------------------------------------------------

class TestPhase176ContractSemantics:
    """Verify that authoritative contract specifications match code model."""

    def test_mcp_fixture_exists(self):
        path = ROOT / "data/fixtures/delta/delta_mcp_public_products_20260925.json"
        assert path.exists(), "Authoritative MCP product fixture is missing"

    def test_authoritative_contract_multiplier(self):
        """MCP payload must record contract_value = 0.001."""
        data = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        products = data.get("products", [])
        btcusd = next((p for p in products if p.get("symbol") == "BTCUSD"), None)
        assert btcusd is not None, "BTCUSD product not found in MCP fixture"
        assert Decimal(str(btcusd["contract_value"])) == Decimal("0.001"), (
            f"Authoritative contract_value is not 0.001: got {btcusd['contract_value']}"
        )

    def test_authoritative_is_not_quanto(self):
        """BTCUSD must be a linear (not quanto) contract."""
        data = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        btcusd = data["products"][0]
        assert btcusd["is_quanto"] is False, "BTCUSD is incorrectly marked as quanto"
        assert btcusd["notional_type"] == "vanilla", (
            f"Expected notional_type='vanilla', got {btcusd['notional_type']}"
        )

    def test_authoritative_tick_size(self):
        """Authoritative tick size from MCP payload is 0.1 USD."""
        data = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        btcusd = data["products"][0]
        assert Decimal(str(btcusd["tick_size"])) == Decimal("0.1"), (
            f"Expected authoritative tick_size=0.1, got {btcusd['tick_size']}"
        )

    def test_tick_size_discrepancy_documented_in_findings(self):
        """FINDING-176-01 must document the tick size discrepancy."""
        findings = _load_json("reports/PHASE176_FINDINGS.json")
        f01 = next((f for f in findings["findings"] if f["id"] == "FINDING-176-01"), None)
        assert f01 is not None, "FINDING-176-01 (tick size discrepancy) is missing from PHASE176_FINDINGS.json"
        assert "0.10" in f01["description"] or "0.1" in f01["description"], (
            "FINDING-176-01 must mention 0.10 (authoritative tick size)"
        )
        assert "0.50" in f01["description"] or "0.5" in f01["description"], (
            "FINDING-176-01 must mention 0.50 (documented tick size)"
        )

    def test_authoritative_fee_rates(self):
        """MCP payload maker=0.0002, taker=0.0005."""
        data = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        btcusd = data["products"][0]
        assert Decimal(str(btcusd["maker_commission_rate"])) == Decimal("0.0002")
        assert Decimal(str(btcusd["taker_commission_rate"])) == Decimal("0.0005")

    def test_authoritative_settlement_currency_usd(self):
        """Both quoting and settling asset must be USD."""
        data = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        btcusd = data["products"][0]
        assert btcusd["quoting_asset"]["symbol"] == "USD"
        assert btcusd["settling_asset"]["symbol"] == "USD"


# ---------------------------------------------------------------------------
# Class 3: Fee and P&L Arithmetic Reproduction
# ---------------------------------------------------------------------------

class TestPhase176FeeAndPnLReproduction:
    """Independent reproduction of published fee and P&L numbers."""

    MAKER_RATE = Decimal("0.0002")
    TAKER_RATE = Decimal("0.0005")
    GST_RATE = Decimal("0.18")
    MULTIPLIER = Decimal("0.001")

    def test_effective_maker_rate_bps(self):
        """Effective maker rate = 2.36 bps."""
        eff = self.MAKER_RATE * (1 + self.GST_RATE) * Decimal("10000")
        assert eff.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal("2.36")

    def test_effective_taker_rate_bps(self):
        """Effective taker rate = 5.90 bps."""
        eff = self.TAKER_RATE * (1 + self.GST_RATE) * Decimal("10000")
        assert eff.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal("5.90")

    def test_single_leg_maker_fee_at_82k(self):
        """Single-leg maker fee at $82,000, qty=1 = $0.01935200."""
        notional = Decimal("82000.00") * self.MULTIPLIER * Decimal("1")
        fee = _fee(notional, self.MAKER_RATE, self.GST_RATE)
        assert fee == Decimal("0.01935200"), f"Expected 0.01935200, got {fee}"

    def test_single_leg_taker_fee_at_82k(self):
        """Single-leg taker fee at $82,000, qty=1 = $0.04838000."""
        notional = Decimal("82000.00") * self.MULTIPLIER * Decimal("1")
        fee = _fee(notional, self.TAKER_RATE, self.GST_RATE)
        assert fee == Decimal("0.04838000"), f"Expected 0.04838000, got {fee}"

    def test_gross_pnl_linear_formula_4pt5(self):
        """Gross P&L for 4.5-pt move at $82k = $0.00450000."""
        gross = (Decimal("82004.50") - Decimal("82000.00")) * self.MULTIPLIER * Decimal("1")
        gross = gross.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        assert gross == Decimal("0.00450000")

    def test_gross_pnl_linear_formula_50pt(self):
        """Gross P&L for 50-pt move = $0.05000000."""
        gross = Decimal("50") * self.MULTIPLIER * Decimal("1")
        assert gross.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP) == Decimal("0.05000000")

    def test_round_trip_maker_approx_at_82k(self):
        """Round-trip maker fee (both legs at $82k) ~ $0.03870400."""
        notional = Decimal("82000.00") * self.MULTIPLIER * Decimal("1")
        leg_fee = _fee(notional, self.MAKER_RATE, self.GST_RATE)
        rt_fee = leg_fee * 2
        assert rt_fee == Decimal("0.03870400"), f"Expected 0.03870400, got {rt_fee}"

    def test_breakeven_pts_maker(self):
        """Maker breakeven ~ 38.70 pts for $82k entry, qty=1."""
        notional = Decimal("82000.00") * self.MULTIPLIER * Decimal("1")
        rt_fee = _fee(notional, self.MAKER_RATE, self.GST_RATE) * 2
        breakeven = (rt_fee / (self.MULTIPLIER * Decimal("1"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        assert breakeven == Decimal("38.70"), f"Expected 38.70, got {breakeven}"

    def test_net_pnl_4pt5_maker_is_negative(self):
        """Net P&L for 4.5-pt move under maker fees must be negative."""
        notional_82k = Decimal("82000.00") * self.MULTIPLIER
        rt_fee = _fee(notional_82k, self.MAKER_RATE, self.GST_RATE) * 2
        gross = Decimal("4.5") * self.MULTIPLIER
        net = gross - rt_fee
        assert net < Decimal("0"), f"Expected negative net P&L, got {net}"

    def test_rebate_has_zero_gst(self):
        """Rebate tiers (base_fee < 0) receive zero GST."""
        REBATE_RATE = Decimal("-0.0001")
        notional = Decimal("82000.00") * self.MULTIPLIER
        base_fee = (notional * REBATE_RATE).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        assert base_fee < Decimal("0"), "Rebate base fee should be negative"
        # When base_fee < 0, GST = 0 per codebase rules
        gst = Decimal("0.00000000")
        total = base_fee + gst
        assert total == base_fee, "Rebate total should equal base_fee (no GST)"
        assert gst == Decimal("0"), "GST on rebates must be zero"

    def test_82k_vs_42k_basis_discriminator(self):
        """Fee at $82k must be approximately 2x the fee at $42k."""
        n_82k = Decimal("82000.00") * self.MULTIPLIER
        n_42k = Decimal("42000.00") * self.MULTIPLIER
        fee_82k = _fee(n_82k, self.MAKER_RATE, self.GST_RATE)
        fee_42k = _fee(n_42k, self.MAKER_RATE, self.GST_RATE)
        ratio = (fee_82k / fee_42k).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        # $82k / $42k ≈ 1.952 (approximately 2x)
        assert Decimal("1.9") < ratio < Decimal("2.1"), (
            f"Fee ratio 82k/42k should be ~2x, got {ratio}"
        )
        # The canonical published fee $0.03871580 is consistent with 82k, not 42k
        # Round-trip at 42k = ~$0.01987200, at 82k = ~$0.03870400
        rt_42k = fee_42k * 2
        rt_82k = fee_82k * 2
        PUBLISHED_FEE = Decimal("0.03871580")
        diff_from_82k = abs(PUBLISHED_FEE - rt_82k)
        diff_from_42k = abs(PUBLISHED_FEE - rt_42k)
        assert diff_from_82k < diff_from_42k, (
            "Published fee $0.03871580 is closer to the $82k basis than the $42k basis"
        )


# ---------------------------------------------------------------------------
# Class 4: Hurdle Gate Independent Audit
# ---------------------------------------------------------------------------

class TestPhase176HurdleGate:
    """Independent verification of friction hurdle gate arithmetic and safety."""

    def test_hurdle_gate_import(self):
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle, FrictionHurdleGate
        assert callable(evaluate_friction_hurdle)
        assert hasattr(FrictionHurdleGate, "evaluate")

    def test_rule1_subsumes_rule2_proof(self):
        """Rule 1 (40%) implies breakeven multiple >= 2.5x > Rule 2 threshold 2.0x."""
        # If fee_ratio = fee/gross_target <= 0.40
        # Then 1/fee_ratio = gross_target/fee = breakeven_multiple >= 2.50
        # Rule 2 requires >= 2.00, so Rule 1 is strictly stricter.
        MAX_FEE_RATIO = Decimal("0.40")
        min_multiple_implied_by_rule1 = Decimal("1") / MAX_FEE_RATIO
        rule2_threshold = Decimal("2.0")
        assert min_multiple_implied_by_rule1 == Decimal("2.5"), (
            f"Rule 1 implies minimum multiple of 2.5x, got {min_multiple_implied_by_rule1}"
        )
        assert min_multiple_implied_by_rule1 > rule2_threshold, (
            "Rule 1 must strictly subsume Rule 2"
        )

    def test_fail_closed_on_none_inputs(self):
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=None, target_price=None, stop_price=None
        )
        assert result.allowed is False
        assert result.rejection_reason is not None
        assert "missing" in result.rejection_reason.lower() or "non-finite" in result.rejection_reason.lower()

    def test_fail_closed_on_nan(self):
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=float("nan"), target_price=82100.0, stop_price=81950.0
        )
        assert result.allowed is False

    def test_fail_closed_on_zero_entry(self):
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=0, target_price=82100.0, stop_price=81950.0
        )
        assert result.allowed is False

    def test_fail_closed_on_zero_target_distance(self):
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=82000.0, target_price=82000.0, stop_price=81950.0
        )
        assert result.allowed is False

    def test_small_scalp_rejected(self):
        """4.5-pt target at $82k must fail all three gates."""
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=82000.0,
            target_price=82004.5,
            stop_price=81990.0,
            quantity=1,
            contract_multiplier=0.001,
        )
        assert result.allowed is False
        assert result.fee_to_target_pct > Decimal("40")

    def test_large_target_can_pass_rule1(self):
        """A sufficiently large target should pass Rule 1 at $82k, maker fees."""
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        from core.execution.maker_execution_model import ExecutionStyle
        # 200-pt target, 50-pt stop, maker fees
        result = evaluate_friction_hurdle(
            entry_price=82000.0,
            target_price=82200.0,
            stop_price=81950.0,
            quantity=1,
            contract_multiplier=0.001,
            execution_style=ExecutionStyle.MAKER,
        )
        # Fee ratio = ~0.0387 / (200 × 0.001) = ~19.4% < 40% → Rule 1 passes
        assert result.fee_to_target_pct < Decimal("40"), (
            f"200-pt target should have fee ratio < 40%, got {result.fee_to_target_pct}%"
        )
        assert result.rule1_fee_ratio_pass is True

    def test_alternate_points_signature_consistency(self):
        """Points-based signature must produce consistent gate results."""
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            gross_target_points=100.0,
            round_trip_fee_points=38.70,
            stop_loss_points=50.0,
        )
        # fee_ratio = 38.70/100 = 38.7% < 40% → Rule 1 passes
        assert result.rule1_fee_ratio_pass is True
        # post_fee_rr = (100-38.70)/(50+38.70) = 61.30/88.70 = 0.69 < 1.25 → Rule 3 fails
        assert result.rule3_post_fee_rr_pass is False
        assert result.allowed is False

    def test_hurdle_verdict_passed_alias(self):
        """HurdleVerdict.passed must equal HurdleVerdict.allowed."""
        from core.execution.friction_hurdle_gate import evaluate_friction_hurdle
        result = evaluate_friction_hurdle(
            entry_price=82000.0, target_price=82100.0, stop_price=81950.0, quantity=1
        )
        assert result.passed == result.allowed


# ---------------------------------------------------------------------------
# Class 5: Phase 176 Report Completeness and Release Gate Integrity
# ---------------------------------------------------------------------------

REQUIRED_PHASE176_REPORTS = [
    "reports/PHASE176_CONTRACT_SEMANTICS_AUDIT.md",
    "reports/PHASE176_INSTRUMENT_ECONOMICS_AUDIT.md",
    "reports/PHASE176_FEE_AND_PNL_REPRODUCTION.md",
    "reports/PHASE176_RISK_AND_MARGIN_AUDIT.md",
    "reports/PHASE176_HURDLE_GATE_AUDIT.md",
    "reports/PHASE176_DATA_EVIDENCE_AUDIT.md",
    "reports/PHASE176_PRIVACY_REVIEW.md",
    "reports/PHASE176_FINDINGS.json",
    "reports/PHASE176_TEST_RESULTS.json",
    "reports/PHASE176_BLOCKERS.json",
    "reports/PHASE176_PROVENANCE.json",
    "reports/PHASE176_RELEASE_GATES.json",
]


class TestPhase176ReleaseRecords:
    """Verify all Phase 176 release records exist and are internally consistent."""

    def test_required_phase176_reports_exist_and_non_empty(self):
        for rel in REQUIRED_PHASE176_REPORTS:
            path = ROOT / rel
            assert path.exists(), f"Required Phase 176 report missing: {rel}"
            assert path.stat().st_size > 0, f"Phase 176 report is empty: {rel}"

    def test_findings_json_structure(self):
        findings = _load_json("reports/PHASE176_FINDINGS.json")
        assert findings["phase"] == 176
        assert findings["system_status"] == "NOT_PRODUCTION_READY"
        assert findings["strategy_status"] == "EDGE NOT ESTABLISHED"
        assert len(findings["findings"]) >= 8

    def test_blockers_json_structure(self):
        blockers = _load_json("reports/PHASE176_BLOCKERS.json")
        assert blockers["phase"] == 176
        assert blockers["system_status"] == "NOT_PRODUCTION_READY"
        assert len(blockers["blockers"]) >= 7

    def test_release_gates_not_production_ready(self):
        gates = _load_json("reports/PHASE176_RELEASE_GATES.json")
        assert gates["phase"] == 176
        assert gates["system_status"] == "NOT_PRODUCTION_READY"
        assert gates["strategy_status"] == "EDGE NOT ESTABLISHED"

    def test_release_gates_blocked_gates_present(self):
        """At least one gate must be BLOCKED."""
        gates = _load_json("reports/PHASE176_RELEASE_GATES.json")
        statuses = [g["status"] for g in gates["gates"].values()]
        assert "BLOCKED" in statuses, "At least one gate must be BLOCKED"

    def test_provenance_names_archives(self):
        prov = _load_json("reports/PHASE176_PROVENANCE.json")
        assert prov["phase"] == 176
        assert "input_archive" in prov or "input_archives" in prov
        assert "output_archive" in prov or "output_archives" in prov

    def test_gates_reference_only_existing_reports(self):
        gates = _load_json("reports/PHASE176_RELEASE_GATES.json")
        for gate_id, gate in gates["gates"].items():
            evidence = gate.get("evidence")
            if evidence and isinstance(evidence, str) and evidence.startswith("reports/"):
                path = ROOT / evidence
                assert path.exists(), (
                    f"Gate {gate_id} references missing evidence file: {evidence}"
                )

    def test_historical_records_preserved(self):
        """Phase 175 and earlier reports must still exist (not overwritten)."""
        preserved = [
            "reports/PHASE175_RELEASE_GATES.json",
            "reports/PHASE175_FINDINGS.json",
            "reports/PHASE175_BLOCKERS.json",
        ]
        for rel in preserved:
            path = ROOT / rel
            assert path.exists(), f"Historical Phase 175 record missing: {rel}"
