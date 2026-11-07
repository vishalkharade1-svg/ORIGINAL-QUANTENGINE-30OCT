"""
====================================================

QuantEngine

Research Lab -- exit models (Phase 9B)

Derive the EXPERIMENTAL stop and target levels from the source
opportunity economics plus the stop_mode / target_mode / rr in an
ExperimentConfig.

EXISTING_STOP / EXISTING_TARGET copy the frozen original levels.
ATR uses the decision-time ATR (reused core indicator).
STRUCTURAL / SWING / FIBONACCI fall back to the existing levels
unless the config carries a custom ratio (kept extensible; the
full structural/Fib implementations belong to later phases).
CUSTOM applies custom_stop_ratio / custom_target_ratio against
the source risk width.
FIXED_RR derives target from entry and risk = |entry - stop| * rr.

All outputs are causal (only decision-bar-and-prior facts).
====================================================
"""

LONG = "BULLISH"
SHORT = "BEARISH"


def derive_stop(config, source_entry, source_stop, atr, direction):
    mode = config.stop_mode
    if mode == "EXISTING_STOP":
        return float(source_stop)
    if mode == "ATR":
        mult = config.custom_stop_ratio if config.custom_stop_ratio else 1.5
        return _stop_from_atr(source_entry, atr, mult, direction)
    if mode == "CUSTOM":
        return _stop_from_atr(source_entry, atr, config.custom_stop_ratio, direction) \
            if config.custom_stop_ratio else float(source_stop)
    # STRUCTURAL / SWING fall back to the existing stop for now.
    return float(source_stop)


def derive_target(config, entry_price, stop_price, source_target, atr, direction):
    mode = config.target_mode
    if mode == "EXISTING_TARGET":
        return float(source_target)
    risk = abs(entry_price - stop_price)
    if mode == "FIXED_RR":
        return _target_from_rr(entry_price, stop_price, risk, config.rr, direction)
    if mode == "ATR":
        mult = config.custom_target_ratio if config.custom_target_ratio else config.rr
        return _target_from_atr(entry_price, atr, mult, direction) \
            if atr else _target_from_rr(entry_price, stop_price, risk, config.rr, direction)
    if mode == "CUSTOM":
        if config.custom_target_ratio:
            return _target_from_rr(
                entry_price, stop_price, risk, config.custom_target_ratio, direction
            )
        return float(source_target)
    # STRUCTURAL / FIBONACCI fall back to existing target for now.
    return float(source_target)


def _stop_from_atr(entry, atr, mult, direction):
    if atr is None or atr <= 0:
        return entry * (0.95 if direction == LONG else 1.05)
    distance = mult * atr
    return entry - distance if direction == LONG else entry + distance


def _target_from_rr(entry, stop, risk, rr, direction):
    if risk <= 0:
        return float(stop)
    return entry + (rr * risk) if direction == LONG else entry - (rr * risk)


def _target_from_atr(entry, atr, mult, direction):
    return entry + (mult * atr) if direction == LONG else entry - (mult * atr)
