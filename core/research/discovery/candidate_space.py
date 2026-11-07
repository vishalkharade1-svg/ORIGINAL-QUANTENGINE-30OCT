"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- candidate space

The candidate parameter vocabulary is DERIVED from the frozen 9B
ExperimentConfig schema (the exact fields the frozen 9C grid accepts)
and from the frozen 9C supported-entry-model vocabulary. Anything else
fails LOUDLY -- discovery never invents parameters the research surface
does not support, and never guesses at unsupported ones silently.

validate_overrides() is the single fail-loud gate every hypothesis must
pass before it is scheduled, and again inside the runner before the
grid is executed (defense in depth).

Also asserts the 9J boundary: only supported research axes may appear;
an unsupported axis or a KNOWN_UNSUPPORTED entry model raises ValueError
with the exact supported vocabulary named.
====================================================
"""

from core.research.lab.experiment_config import ExperimentConfig
from core.research.counterfactual.counterfactual_config import (
    SUPPORTED_ENTRY_MODELS,
    KNOWN_UNSUPPORTED_ENTRY_MODELS,
)

# The full supported 9B/9C parameter vocabulary = the canonical field
# names of the frozen ExperimentConfig (what to_params() / grid consume).
SUPPORTED_AXES = tuple(sorted(ExperimentConfig.__dataclass_fields__.keys()))

STOP_MODES = ("EXISTING_STOP", "ATR", "STRUCTURAL", "SWING", "CUSTOM")
TARGET_MODES = (
    "EXISTING_TARGET", "FIXED_RR", "ATR", "STRUCTURAL",
    "FIBONACCI", "CUSTOM",
)

_NUMERIC_AXES = frozenset((
    "entry_offset",
    "entry_offset_atr",
    "confirmation_distance",
    "breakout_buffer",
    "retest_tolerance",
    "max_entry_distance",
    "custom_stop_ratio",
    "custom_target_ratio",
    "rr",
))

_KNOWN_UNSUPPORTED = frozenset(KNOWN_UNSUPPORTED_ENTRY_MODELS)


def vocabulary():
    """Deterministic description of the candidate space (reporting)."""
    return {
        "derived_from": "9B ExperimentConfig schema + 9C entry-model vocabulary",
        "supported_axes": list(SUPPORTED_AXES),
        "entry_models_supported": list(SUPPORTED_ENTRY_MODELS),
        "entry_models_known_unsupported": list(
            KNOWN_UNSUPPORTED_ENTRY_MODELS
        ),
        "never_invented_axes": True,
    }


def _require_iterable(axis, values):
    if values is None:
        raise ValueError(
            f"axis {axis!r} requires a non-empty value list"
        )
    if isinstance(values, (str, bytes)):
        raise ValueError(
            f"axis {axis!r} values must be a list/tuple of values, "
            f"got scalar {values!r}"
        )
    try:
        list(values)
    except TypeError:
        raise ValueError(
            f"axis {axis!r} values must be an iterable, got {values!r}"
        )
    if len(list(values)) == 0:
        raise ValueError(f"axis {axis!r} requires a non-empty value list")


def _require_number(axis, value):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"axis {axis!r} expects numeric values, got {value!r}"
        )


def validate_overrides(overrides):
    """Fail loudly on unknown axes or unsupported values.

    Returns a deterministically ordered (sorted-by-axis) dict that the
    grid consumes; caller insertion order is NOT trusted for identity.
    """
    if not isinstance(overrides, dict):
        raise TypeError(
            "overrides must be a dict of axis -> value list"
        )

    for axis, values in overrides.items():
        if axis == "changed_filters":
            _require_iterable(axis, values)
            for v in values:
                if not isinstance(v, (tuple, list)):
                    raise ValueError(
                        "changed_filters grid values must be tuples/lists "
                        f"of filter names, got {v!r}"
                    )
                for name in v:
                    if not isinstance(name, str) or not name:
                        raise ValueError(
                            "changed_filters names must be non-empty "
                            f"strings, got {name!r}"
                        )
            continue

        if axis not in SUPPORTED_AXES:
            raise ValueError(
                "unsupported experiment parameter axis "
                f"{axis!r}; supported axes: {SUPPORTED_AXES}"
            )
        _require_iterable(axis, values)

        for value in values:
            if axis == "entry_model":
                if value not in SUPPORTED_ENTRY_MODELS:
                    raise ValueError(
                        f"unsupported entry model {value!r}: only "
                        f"{SUPPORTED_ENTRY_MODELS} are supported"
                        + (
                            f" (known unsupported: "
                            f"{sorted(_KNOWN_UNSUPPORTED)})"
                            if value in _KNOWN_UNSUPPORTED
                            else ""
                        )
                    )
            elif axis == "stop_mode":
                if value not in STOP_MODES:
                    raise ValueError(
                        f"unsupported stop_mode {value!r}; "
                        f"supported: {STOP_MODES}"
                    )
            elif axis == "target_mode":
                if value not in TARGET_MODES:
                    raise ValueError(
                        f"unsupported target_mode {value!r}; "
                        f"supported: {TARGET_MODES}"
                    )
            elif axis == "expiry":
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value <= 0
                ):
                    raise ValueError(
                        "expiry grid values must be a positive int "
                        f"(or None), got {value!r}"
                    )
            elif axis == "rr":
                _require_number(axis, value)
                if value is not None and value <= 0:
                    raise ValueError(
                        f"rr grid values must be > 0, got {value!r}"
                    )
            elif axis in _NUMERIC_AXES:
                _require_number(axis, value)
            else:
                raise ValueError(
                    f"unsupported experiment parameter axis {axis!r}"
                )

    return dict(sorted(overrides.items()))


def supported_axes_snapshot():
    """The exact canonical field inventory of the frozen 9B schema."""
    return {
        "axes": list(SUPPORTED_AXES),
        "n_axes": len(SUPPORTED_AXES),
        "schema": "ExperimentConfig (frozen, Phase 9B)",
    }