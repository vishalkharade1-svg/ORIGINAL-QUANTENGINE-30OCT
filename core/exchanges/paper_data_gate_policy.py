"""Shared policy validation for the optional paper market-data quality gate.

Compatibility mode remains the default. Deployments that want new runtime
construction to fail closed can set ``required=True`` and must provide a
finite, non-negative maximum candle age.
"""

import math


def validate_paper_data_gate_config(max_age_seconds, required=False, now_provider=None):
    """Return a normalized threshold or raise on invalid/required-missing config."""
    if not isinstance(required, bool):
        raise ValueError("market_data_gate_required must be a boolean")
    if max_age_seconds is None:
        if required:
            raise ValueError(
                "market_data_max_age_seconds is required when market_data_gate_required=True"
            )
        threshold = None
    else:
        # bool is a numeric subtype in Python, but True/False are not meaningful
        # age thresholds and accepting them would silently mean 1 or 0 seconds.
        if isinstance(max_age_seconds, bool):
            raise ValueError("market_data_max_age_seconds must be finite and non-negative")
        try:
            threshold = float(max_age_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "market_data_max_age_seconds must be finite and non-negative"
            ) from exc
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("market_data_max_age_seconds must be finite and non-negative")
    if now_provider is not None and not callable(now_provider):
        raise ValueError("market_data_now_provider must be callable")
    return threshold
