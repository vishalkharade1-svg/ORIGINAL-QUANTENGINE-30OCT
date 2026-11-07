import unittest
from unittest.mock import patch


class TestBacktesterEconomicsWiring66(unittest.TestCase):
    def test_configured_nonzero_costs_are_consumed_by_default(self):
        from backtesting.backtester import Backtester
        from core.risk.costs import CostSpec

        configured = CostSpec(per_trade=1.0, rate=0.001, slippage_bps=5.0)
        with patch("core.risk.costs.from_settings", return_value=configured):
            bt = Backtester.__new__(Backtester)
            bt.__init__(pipeline=None, event_bus=None, simulator=None)
        self.assertEqual(bt.cost_spec, configured)

    def test_explicit_zero_settings_preserve_legacy_cost_passthrough(self):
        from backtesting.backtester import Backtester
        from core.risk.costs import CostSpec

        zero = CostSpec()
        with patch("core.risk.costs.from_settings", return_value=zero):
            bt = Backtester.__new__(Backtester)
            bt.__init__(pipeline=None, event_bus=None, simulator=None)
        self.assertIsNone(bt.cost_spec)

    def test_explicit_cost_spec_always_wins(self):
        from backtesting.backtester import Backtester
        from core.risk.costs import CostSpec

        explicit = CostSpec(per_trade=2.0, rate=0.002, slippage_bps=7.0)
        configured = CostSpec(per_trade=1.0, rate=0.001, slippage_bps=5.0)
        with patch("core.risk.costs.from_settings", return_value=configured):
            bt = Backtester.__new__(Backtester)
            bt.__init__(pipeline=None, event_bus=None, simulator=None,
                        cost_spec=explicit)
        self.assertEqual(bt.cost_spec, explicit)


if __name__ == "__main__":
    unittest.main()
