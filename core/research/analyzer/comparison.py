"""
====================================================

QuantEngine

Research Analyzer -- experiment comparison (Phase 9D)

Deterministic diff between two metric bundles. Answers:

    baseline vs experiment       (compare_baseline)
    experiment vs experiment      (compare_experiments)

It retains the exact experiment identity + config provenance and
reports deltas as REPORTS (incremental fills / wins / losses, delta
expectancy / PF / MAE / MFE, incremental R and PnL). It NEVER ranks
configurations as "best" and NEVER recommends a production change.

PF deltas handle infinities deterministically and never produce NaN.
====================================================
"""


def _delta(a, b):
    """b - a with inf-safe arithmetic (never NaN)."""
    if a == b:
        return 0.0
    if a == float("inf") and b == float("inf"):
        return 0.0
    if b == float("inf"):
        return float("inf")
    if a == float("inf"):
        return -float("inf")
    return float(b) - float(a)


class ExperimentComparison:
    """One baseline-vs-experiment (or a-vs-b) comparison."""

    def __init__(self, experiment_id, config, baseline_id,
                 baseline_metrics, comparison_metrics, kind):
        self.experiment_id = experiment_id
        self.config = config
        self.baseline_id = baseline_id
        self.baseline_metrics = dict(baseline_metrics or {})
        self.comparison_metrics = dict(comparison_metrics or {})
        self.kind = kind

        base, exp = self.baseline_metrics, self.comparison_metrics
        self.incremental_fills = _delta(base.get("filled", 0), exp.get("filled", 0))
        self.incremental_wins = _delta(base.get("wins", 0), exp.get("wins", 0))
        self.incremental_losses = _delta(base.get("losses", 0), exp.get("losses", 0))
        self.incremental_unsettled = _delta(
            base.get("unsettled", 0), exp.get("unsettled", 0)
        )
        self.incremental_R = _delta(base.get("total_R", 0), exp.get("total_R", 0))
        self.incremental_pnl = _delta(base.get("net_pnl", 0), exp.get("net_pnl", 0))
        self.delta_expectancy = _delta(
            base.get("expectancy", 0), exp.get("expectancy", 0)
        )
        self.delta_win_rate = _delta(base.get("win_rate", 0), exp.get("win_rate", 0))
        self.delta_pf = _delta(base.get("profit_factor", 0),
                               exp.get("profit_factor", 0))
        self.delta_avg_mae = _delta(base.get("avg_MAE", 0), exp.get("avg_MAE", 0))
        self.delta_median_mae = _delta(
            base.get("median_MAE", 0), exp.get("median_MAE", 0)
        )
        self.delta_avg_mfe = _delta(base.get("avg_MFE", 0), exp.get("avg_MFE", 0))
        self.delta_median_mfe = _delta(
            base.get("median_MFE", 0), exp.get("median_MFE", 0)
        )
        self.baseline_sample = base.get("settled", 0)
        self.comparison_sample = exp.get("settled", 0)

    def to_dict(self):
        return {
            "kind": self.kind,
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "config": self.config.to_dict() if self.config else {},
            "baseline_sample": self.baseline_sample,
            "comparison_sample": self.comparison_sample,
            "incremental_fills": self.incremental_fills,
            "incremental_wins": self.incremental_wins,
            "incremental_losses": self.incremental_losses,
            "incremental_unsettled": self.incremental_unsettled,
            "incremental_R": self.incremental_R,
            "incremental_pnl": self.incremental_pnl,
            "delta_expectancy": self.delta_expectancy,
            "delta_win_rate": self.delta_win_rate,
            "delta_pf": self.delta_pf,
            "delta_avg_mae": self.delta_avg_mae,
            "delta_median_mae": self.delta_median_mae,
            "delta_avg_mfe": self.delta_avg_mfe,
            "delta_median_mfe": self.delta_median_mfe,
        }


def compare_baseline(experiment_id, config, baseline_id,
                     baseline_metrics, experiment_metrics):
    """baseline vs experiment deltas."""
    return ExperimentComparison(
        experiment_id=experiment_id,
        config=config,
        baseline_id=baseline_id,
        baseline_metrics=baseline_metrics,
        comparison_metrics=experiment_metrics,
        kind="BASELINE_VS_EXPERIMENT",
    )


def compare_experiments(metrics_a, metrics_b, id_a, id_b,
                        config_a, config_b, baseline_id):
    """experiment A vs experiment B deltas (b - a)."""
    return ExperimentComparison(
        experiment_id=f"{id_b}",
        config=config_b,
        baseline_id=baseline_id,
        baseline_metrics=metrics_a,
        comparison_metrics=metrics_b,
        kind="EXPERIMENT_VS_EXPERIMENT",
    )