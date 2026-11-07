"""
====================================================

QuantEngine

Counterfactual Simulation -- configuration (Phase 9C)

An immutable configuration describing EXACTLY what is being
counterfactually simulated (entry model / RR / expiry / entry
offset / stop / target geometry) plus an EXPLICIT trade-outcome
horizon.

It wraps the deterministic ExperimentConfig (9B) machinery and adds
an explicit validation contract: unknown or unsupported parameters
fail loudly rather than silently inventing behavior. Unsupported
entry models (canonical FVG_RETRACE / DISPLACEMENT_RETEST, which
are MEASURED but NOT implemented as decisers) raise at construction
so a caller can prove it has no decider instead of guessing.

outcome_bars defines the trade-outcome horizon -- the max number of
bars evaluated AFTER a fill. None means "to the end of the supplied
series" (an explicit, documented contract); any integer caps the
evaluation. This prevents an opportunity from silently scanning the
whole dataset when that is not intended.

Deterministic identity: reuses the 9B experiment_id_for hash scheme
over the exact params + outcome_bars + baseline id -- NO random
UUIDs, no timestamps.
====================================================
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

from core.execution.entry_model import (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)
from core.research.lab.experiment_config import ExperimentConfig
from core.research.lab.experiment_runner import experiment_id_for

# Entry modes that have a canonical causal decider in the frozen
# production entry-model routing. Anything else is UNSUPPORTED and
# fails loudly at construction rather than inventing behavior.
SUPPORTED_ENTRY_MODELS = (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)

KNOWN_UNSUPPORTED_ENTRY_MODELS = ("FVG_RETRACE", "DISPLACEMENT_RETEST")

# ExperimentConfig fields a counterfactual is allowed to change.
_SUPPORTED_FIELDS = frozenset(ExperimentConfig.__dataclass_fields__)


@dataclass(frozen=True)
class _IdCarrier:
    """Tiny frozen record whose to_params() feeds experiment_id_for
    with the FULL deterministic identity (params + outcome horizon +
    baseline). Reuses the 9B hash scheme with no duplication."""

    merged: dict = field(default_factory=dict)

    def to_params(self):
        return dict(self.merged)

    def to_dict(self):
        return dict(self.merged)


@dataclass(frozen=True)
class CounterfactualConfig:
    """Immutable counterfactual configuration.

    params:       supported experiment fields (ExperimentConfig)
    outcome_bars: explicit trade-outcome horizon after a fill
                  (None = to end of series; else max bars evaluated)
    baseline_id:  the frozen production baseline measured against
    """

    params: dict = field(default_factory=dict)
    outcome_bars: object = None
    baseline_id: str = "baseline"

    # -------------------------------------------------

    def __post_init__(self):
        unknown = set(self.params) - _SUPPORTED_FIELDS
        if unknown:
            raise ValueError(
                "Unknown counterfactual parameter(s): "
                f"{sorted(unknown)}. Supported: {sorted(_SUPPORTED_FIELDS)}"
            )
        mode = self.params.get("entry_model", ENTRY_MODE_BREAKOUT_CONTINUATION)
        if mode not in SUPPORTED_ENTRY_MODELS:
            raise ValueError(
                f"Unsupported entry model {mode!r}: "
                f"supported={SUPPORTED_ENTRY_MODELS} "
                f"(known-unimplemented: {KNOWN_UNSUPPORTED_ENTRY_MODELS}). "
                "Refusing to invent behavior for a non-decidable model."
            )
        if self.outcome_bars is not None and (
            not isinstance(self.outcome_bars, int) or self.outcome_bars <= 0
        ):
            raise ValueError(
                f"outcome_bars must be a positive int or None, got {self.outcome_bars!r}"
            )

    # -------------------------------------------------

    def to_config(self):
        """Materialize the underlying deterministic 9B ExperimentConfig
        (from the validated experiment params ONLY -- outcome horizon
        is a 9C concept and stays out of the 9B config)."""
        return ExperimentConfig(**self.params)

    def experiment_id(self):
        """Deterministic identity including the outcome horizon."""
        merged = {
            **self.to_config().to_params(),
            "outcome_bars": self.outcome_bars,
        }
        return experiment_id_for(_IdCarrier(merged), self.baseline_id)

    def to_dict(self):
        return {
            "baseline_id": self.baseline_id,
            "params": dict(self.params),
            "outcome_bars": self.outcome_bars,
            "experiment_id": self.experiment_id(),
        }

    def __repr__(self):
        return (
            f"CounterfactualConfig(entry={self.params.get('entry_model')},"
            f" rr={self.params.get('rr')}, expiry={self.params.get('expiry')},"
            f" outcome_bars={self.outcome_bars}, baseline={self.baseline_id})"
        )


# Convenience: a minimal setup-like view the canonical entry models
# read via getattr -- used to hand them the EXPERIMENTAL levels without
# mutating any production or journal object.
def setup_view(experimental_entry, experimental_stop, experimental_target,
               direction, setup_id=""):
    return SimpleNamespace(
        setup_id=setup_id,
        structural_id=setup_id,
        economic_fingerprint="",
        direction=direction,
        entry=experimental_entry,
        stop_loss=experimental_stop,
        take_profit=experimental_target,
    )
