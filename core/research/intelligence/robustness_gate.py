"""
====================================================

QuantEngine

Research Intelligence -- robustness gate (Phase 9E)

A deterministic GATE that folds 9D robustness findings, the recovery
cost and the directional balance into an explicit robustness STATUS
for a candidate recommendation. It NEVER claims statistical
significance and NEVER blocks/enables production -- it only labels
the evidence.

Precedence (first match wins):
   * INSUFFICIENT_SAMPLE  -- settled sample below the comparator floor
   * LOSS_EXPANSION       -- recovery adds more losses than wins
   * OOS_REQUIRED         -- a small-sample in-sample advantage that
                             still needs more data / OOS validation
   * NON_ROBUST           -- a directional-imbalance finding or a
                             non-advantage with warnings
   * ROBUST               -- the favourable case (material advantage,
                             adequate sample, no loss-expansion,
                             no imbalance); the standing "in-sample
                             only / OOS validation" research disclaimer
                             is carried forward as a warning and does
                             not by itself demote the label

This is a deterministic classifier over 9D facts; it is not
statistical inference.
====================================================
"""

_SMALL_SAMPLE = 30
_MIN_SAMPLE = 3


def robustness_status_for(evidence_strength, sample_size, warnings,
                          incremental_wins=0, incremental_losses=0,
                          has_advantage=False):
    """Deterministic robustness label for one candidate."""
    warnings_lower = [w.lower() for w in (warnings or [])]
    joined = " | ".join(warnings_lower)

    if sample_size < _MIN_SAMPLE:
        return "INSUFFICIENT_SAMPLE"

    if incremental_losses > incremental_wins \
            or "recovery increases losses" in joined:
        return "LOSS_EXPANSION"

    if not has_advantage:
        if warnings:
            return "NON_ROBUST"
        return "INCONCLUSIVE"

    # candidate has a material advantage
    if "directional imbalance" in joined:
        return "NON_ROBUST"

    # smaller samples need more data / OOS validation before
    # the advantage can be considered robust.
    if sample_size < _SMALL_SAMPLE:
        return "OOS_REQUIRED"

    return "ROBUST"