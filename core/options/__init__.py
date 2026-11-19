"""Research-only options valuation and exposure tools."""

from core.options.black_scholes import (
    OptionValuation,
    calculate_option_valuation,
    implied_volatility,
    price_european_option,
)
from core.options.position import OptionPositionExposure, scale_option_position
from core.options.scenario import OptionScenarioResult, evaluate_option_scenario
from core.options.chain import OptionChain, OptionChainEntry, OptionContractSnapshot, OptionLeg, build_option_chain

__all__ = (
    "OptionValuation",
    "OptionPositionExposure",
    "OptionScenarioResult",
    "OptionChain",
    "OptionChainEntry",
    "OptionContractSnapshot",
    "OptionLeg",
    "build_option_chain",
    "evaluate_option_scenario",
    "calculate_option_valuation",
    "implied_volatility",
    "price_european_option",
    "scale_option_position",
)
