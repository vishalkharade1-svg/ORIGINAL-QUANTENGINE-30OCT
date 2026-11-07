"""Independent hand-calculation checks for Phase-2 contract math."""

from decimal import Decimal
import unittest

from core.risk.contract_math import (
    ContractKind, ContractSpec, CostModel, gross_stop_loss, size_to_risk_budget, stop_risk,
)


D = Decimal
ZERO_COSTS = CostModel(D("0"), D("0"), D("0"), D("0"), D("0"))


class TestContractMath(unittest.TestCase):
    def test_linear_hand_calculation_and_costs(self):
        spec = ContractSpec(ContractKind.LINEAR, D("0.001"), D("0.5"), D("0.001"), D("0.001"))
        costs = CostModel(D("10"), D("10"), D("0.5"), D("5"), D("0.01"))
        quote = stop_risk(spec, costs, D("2"), D("100000"), D("99000"))
        self.assertEqual(quote.gross_stop_loss, D("2"))  # 2 * .001 * 1000
        self.assertEqual(quote.entry_notional, D("200"))
        # fees=.398, entry+exit slippage=.199, spread=.002, funding=.02
        self.assertEqual(quote.estimated_costs, D("0.6190"))
        self.assertEqual(quote.total_stop_loss, D("2.6190"))

    def test_inverse_hand_calculation(self):
        spec = ContractSpec(ContractKind.INVERSE, D("100"), D("0.5"), D("1"), D("1"))
        # 10 contracts * $100 * (10000 - 9000) / 10000 = $100 loss at stop.
        self.assertEqual(gross_stop_loss(spec, D("10"), D("10000"), D("9000")), D("100"))

    def test_option_premium_is_explicit_linear_premium_math(self):
        spec = ContractSpec(ContractKind.OPTION_PREMIUM, D("0.1"), D("0.01"), D("1"), D("1"))
        self.assertEqual(gross_stop_loss(spec, D("5"), D("20"), D("14")), D("3.0"))

    def test_size_rounds_down_and_includes_costs(self):
        spec = ContractSpec(ContractKind.LINEAR, D("1"), D("0.01"), D("0.1"), D("0.1"))
        result = size_to_risk_budget(spec, ZERO_COSTS, D("10"), D("100"), D("96"))
        self.assertTrue(result.valid)
        self.assertEqual(result.quantity, D("2.5"))
        self.assertEqual(result.risk_quote.total_stop_loss, D("10.0"))
        self.assertFalse(size_to_risk_budget(spec, ZERO_COSTS, D("0.3"), D("100"), D("96")).valid)


if __name__ == "__main__":
    unittest.main()
