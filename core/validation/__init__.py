"""
====================================================

QuantEngine

Validation Layer

Walk-Forward Testing, Monte Carlo and Strategy
Optimizer -- all consuming the canonical Backtester /
PerformanceAnalytics / shared trade objects only.

====================================================

"""

from .walk_forward import (
    WalkForwardFold,
    WalkForwardResult,
    WalkForwardTester,
)

from .monte_carlo import (
    MonteCarloResult,
    MonteCarloSimulator,
)

from .optimizer import (
    OptimizationRun,
    StrategyOptimizer,
)

__all__ = [
    "WalkForwardFold",
    "WalkForwardResult",
    "WalkForwardTester",
    "MonteCarloResult",
    "MonteCarloSimulator",
    "OptimizationRun",
    "StrategyOptimizer",
]