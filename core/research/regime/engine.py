"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- engine

The deterministic orchestrator answering:

   * Under what market conditions does a candidate configuration
     (entry model / RR / stop geometry / expiry / offset / ...) work
     -- and under what conditions does it fail?
   * Is that conditional advantage real (walk-forward) or a lucky
     combination (multiple-testing guard)?
   * Which observed 9F features associate with the outcomes?

Pipeline (read-only over frozen 9A-9J surfaces):

   1. segment -- 9A records -> RegimeObservation (9C category +
      decision-time MarketRegime from the supplied candles);
   2. conditional -- per candidate (strict 9B/9C vocabulary) per
      regime cell: candidate vs frozen baseline INSIDE the cell,
      recoveries, global-vs-within edge, split breadth;
   3. walk-forward -- chronological expanding-train / trailing-test
      windows over the material findings (no shuffle, no leakage);
   4. multiple-testing -- conservative familywise correction over the
      tested (config x dimension) hypotheses;
   5. feature splits -- observed 9F values joined to outcomes;
   6. robustness -- coverage of every finding across directions,
      symbols and temporal windows;
   7. report -- frozen, deterministic, research-only regime report.

Boundaries: never mutates records/candles/dataset; never touches a
ledger/order/account/portfolio/strategy/risk state; no lookahead; no
randomness; no auto-promotion.
====================================================
"""

from core.research.discovery.constants import NEVER_EMITTED
from core.research.regime.detector import (
    detect_regime,
    primary_regime_dimensions,
)
from core.research.regime import (
    segmenter,
    conditional,
    walkforward,
    multiple_testing,
)
from core.research.regime.report import RegimeReport
from research.integrations.delta_mcp_regime_context import (
    summarize_regime_context, regime_context_limitations,
)


class OpportunityDiscoveryEngine:
    """Deterministic phase 9K orchestrator."""

    def __init__(self, candles, min_cell_n=10, delta_threshold=0.15,
                 split_threshold=0.3, lookback=40, atr_period=14,
                 n_windows=3, min_validation_n=3, feature_min_n=5,
                 alpha=0.05):
        self.candles = list(candles or ())
        self.min_cell_n = min_cell_n
        self.delta_threshold = delta_threshold
        self.split_threshold = split_threshold
        self.lookback = lookback
        self.atr_period = atr_period
        self.n_windows = n_windows
        self.min_validation_n = min_validation_n
        self.feature_min_n = feature_min_n
        self.alpha = alpha

    # -------------------------------------------------

    @staticmethod
    def availability():
        return {
            "phase": "9K",
            "requires_external_sdk": False,
            "never_emits": list(NEVER_EMITTED),
            "research_only": True,
        }

    # -------------------------------------------------

    def run(self, records, base_config, candidates, symbol="UNKNOWN",
            dataset=None, dimensions=None):
        """One deterministic regime/opportunity discovery run."""
        records = list(records or ())
        dims = tuple(dimensions) if dimensions else \
            primary_regime_dimensions()

        observations = segmenter.segment_observations(
            records, self.candles,
            lookback=self.lookback, atr_period=self.atr_period)
        cells, findings = conditional.conditional_discovery(
            records, self.candles, base_config, candidates,
            observations,
            min_cell_n=self.min_cell_n,
            delta_threshold=self.delta_threshold,
            split_threshold=self.split_threshold,
            dimensions=dims,
        )

        walk = {}
        for f in findings:
            if f.status not in ("CONDITIONAL", "CONDITIONAL_WEAK"):
                continue
            summary = walkforward.validate_conditional(
                f, observations, records, self.candles, base_config,
                n_windows=self.n_windows,
                min_validation_n=self.min_validation_n)
            walk[f.finding_id] = summary.to_dict()

        splits = conditional.feature_splits(
            dataset, observations, min_n_gate=self.feature_min_n)
        mt = multiple_testing.multiple_testing_summary(
            cells, findings, self.min_cell_n,
            self.delta_threshold, alpha=self.alpha)
        robustness = self._robustness(
            observations, findings)

        limitations = self._limitations(
            observations, cells, findings, splits, walk)
        mcp_context = summarize_regime_context(dataset, symbol=symbol)
        limitations = tuple(sorted(
            limitations + regime_context_limitations(mcp_context)
        ))

        return RegimeReport(
            symbol=symbol,
            dataset_shape={
                "observations": len(observations),
                "by_category": segmenter.by_category(observations),
                "regime_coverage": segmenter.regime_coverage(
                    observations),
                "dimensions": list(dims),
            },
            cells=cells,
            findings=findings,
            feature_splits=splits,
            walk_forward=walk,
            multiple_testing=mt,
            robustness=robustness,
            limitations=limitations,
            next_research=(
                "multi-period OOS re-validation of surviving "
                "conditional findings (9M)",
                "advanced ML + regime discovery over surviving cells "
                "(9L)",
                "research recommendation layer aggregating 9J + 9K "
                "evidence (9N)",
            ),
        )

    # -------------------------------------------------

    @staticmethod
    def _robustness(observations, findings):
        directions = tuple(sorted({
            o.direction for o in observations if o.direction}))
        symbols = tuple(sorted({
            o.symbol for o in observations if o.symbol}))
        coverage = {}
        for f in findings:
            cell = [o for o in observations
                    if o.in_regime(f.dimension, f.label)]
            coverage[f.finding_id] = {
                "directions": {
                    d: sum(1 for o in cell if o.direction == d)
                    for d in directions
                },
                "symbols": {
                    s: sum(1 for o in cell if o.symbol == s)
                    for s in symbols
                },
                "n": len(cell),
            }
        return {
            "directions": list(directions),
            "symbols": list(symbols),
            "per_finding_coverage": coverage,
        }

    # -------------------------------------------------

    @staticmethod
    def _limitations(observations, cells, findings, splits, walk):
        limitations = [
            "regime indicators are structural market research; they "
            "never assert without the minimum-sample gate and never "
            "direct a trade",
            "conditional conclusions are association evidence within "
            "this dataset/config; live profitability is NOT claimed",
            "multiple-testing guard is conservative and descriptive; "
            "survival is not a significance certificate",
        ]
        total = len(observations)
        covered = sum(1 for o in observations if o.regime)
        if covered < total:
            limitations.append(
                "regime segmentation covered %d of %d observations "
                "(the rest lack a decision bar / enough decision-time "
                "window; they are never assigned a fake regime)"
                % (covered, total)
            )
        if not cells:
            limitations.append(
                "no regime cells could be formed -- no records, no "
                "candidate, or no available regime labels"
            )
        if not findings:
            limitations.append(
                "no conditional findings were produced; the run is "
                "empty by evidence, not by omission"
            )
        if not walk:
            limitations.append(
                "no material conditional finding reached walk-forward "
                "validation"
            )
        if not splits:
            limitations.append(
                "no 9F feature evidence was joined to outcomes; "
                "feature splits were NOT synthesized"
            )
        return tuple(sorted(limitations))