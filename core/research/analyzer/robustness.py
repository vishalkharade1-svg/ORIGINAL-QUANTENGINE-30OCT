"""
====================================================

QuantEngine

Research Analyzer -- robustness assessment (Phase 9D)

Lightweight, DETERMINISTIC robustness checks on a comparison. It
flags small samples, directional imbalance, loss expansion and the
absence of out-of-sample evidence. It NEVER claims statistical
significance (no statistical procedure is implemented in this
phase) and never recommends adopting a configuration.

Warnings are plain deterministic strings in a fixed order.
====================================================
"""

_SMALL_SAMPLE = 30
_MIN_SAMPLE = 3


def assess(comparison, experiment_metrics=None, baseline_metrics=None,
           directional_sizes=None):
    """Deterministic warning list for one experiment comparison.

    directional_sizes: {direction: count} for the experiment (from
    the analyzer's directional grouping); used for imbalance flags.
    """
    warnings = []
    exp_metrics = experiment_metrics or {}
    sample = comparison.comparison_sample if comparison else \
        exp_metrics.get("settled", 0)
    incremental_losses = comparison.incremental_losses if comparison else 0
    incremental_wins = comparison.incremental_wins if comparison else 0

    if sample < _MIN_SAMPLE:
        warnings.append(
            f"insufficient sample: only {sample} settled experiment trade(s)"
        )
    elif sample < _SMALL_SAMPLE:
        warnings.append(
            f"small sample: {sample} settled trade(s) -- not "
            "production-adoption evidence"
        )
    if sample < 200 and sample > 0:
        warnings.append(
            "no statistical significance is claimed (deterministic "
            "research facts only)"
        )

    if incremental_losses > incremental_wins:
        warnings.append(
            f"recovery increases losses: +{incremental_losses} losses "
            f"vs +{incremental_wins} wins"
        )

    if directional_sizes:
        total = float(sum(directional_sizes.values()))
        if total > 0:
            minority = min(directional_sizes.values())
            share = minority / total if total else 0.0
            if share < 0.2:
                warnings.append(
                    "directional imbalance: one direction holds "
                    f"{share:.0%} of the experiment sample"
                )

    if comparison is not None:
        improved = (
            comparison.delta_expectancy > 0 or comparison.delta_pf > 0
        )
        if improved:
            warnings.append(
                "suggested improvement is in-sample only; requires OOS "
                "validation before any production consideration"
            )

    warnings.append(
        "in-sample research only; no out-of-sample validation performed"
    )
    return warnings