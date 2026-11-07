"""
====================================================

QuantEngine

Research Lab -- experiment configuration (Phase 9B)

Immutable experiment configuration. Describes ONE alternative
rule set the lab will replay against historical candles.

It is deliberately frozen (frozen dataclass): an experiment can
never be mutated in place, so a sweep is always a fresh config
and a recorded result always identifies exactly the parameters
that produced it.

Counterfactual nature: these are experiment parameters. They are
NOT production defaults and never touch the production strategy /
risk configuration (see Section 15 / 26 of the Phase 9B brief).

====================================================
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExperimentConfig:
    """One immutable alternative rule set for a replay.

    entry_model:      LIMIT_RETEST / BREAKOUT_CONTINUATION /
                      MARKET_CONFIRMATION
    stop_mode:        EXISTING_STOP / ATR / STRUCTURAL / SWING / CUSTOM
    target_mode:      EXISTING_TARGET / FIXED_RR / ATR / STRUCTURAL /
                      FIBONACCI / CUSTOM
    rr:               target / risk ratio (RISK = |entry - stop|)
    expiry:           max bars from the decision bar to seek an entry;
                      None means no expiry (replay to end of series)
    changed_filters:  filters (rejection conditions) that this
                      experiment removes / toggles vs baseline
    """

    # entry model + params
    entry_model: str = "BREAKOUT_CONTINUATION"
    entry_offset: float = 0.0
    entry_offset_atr: float = 0.0
    confirmation_distance: float = 0.0
    breakout_buffer: float = 0.0
    retest_tolerance: float = 0.0
    max_entry_distance: float = 0.0
    expiry: object = None

    # stop / target
    stop_mode: str = "EXISTING_STOP"
    target_mode: str = "FIXED_RR"
    custom_stop_ratio: float = 0.0
    custom_target_ratio: float = 0.0
    rr: float = 2.0

    # which production rejection filters this experiment toggles
    changed_filters: tuple = field(default_factory=tuple)

    # -------------------------------------------------

    def with_filter(self, name):
        """Return a NEW config with `name` toggled in
        changed_filters (immutable; pipe only)."""
        return ExperimentConfig(
            **{
                **self.to_params(),
                "changed_filters": tuple(sorted(set(self.changed_filters) | {name})),
            }
        )

    def with_removed_filter(self, name):
        """Return a NEW config with `name` removed from
        changed_filters (immutable; pipe only)."""
        return ExperimentConfig(
            **{
                **self.to_params(),
                "changed_filters": tuple(
                    sorted(f for f in self.changed_filters if f != name)
                ),
            }
        )

    # -------------------------------------------------

    def to_params(self):
        """Plain dict of all scalar config fields. Used for
        deterministic experiment-id derivation and grid sweeps."""
        return {
            "entry_model": self.entry_model,
            "entry_offset": self.entry_offset,
            "entry_offset_atr": self.entry_offset_atr,
            "confirmation_distance": self.confirmation_distance,
            "breakout_buffer": self.breakout_buffer,
            "retest_tolerance": self.retest_tolerance,
            "max_entry_distance": self.max_entry_distance,
            "expiry": self.expiry,
            "stop_mode": self.stop_mode,
            "target_mode": self.target_mode,
            "custom_stop_ratio": self.custom_stop_ratio,
            "custom_target_ratio": self.custom_target_ratio,
            "rr": self.rr,
            "changed_filters": self.changed_filters,
        }

    def to_dict(self):
        return {
            **self.to_params(),
            "changed_filters": list(self.changed_filters),
        }

    # -------------------------------------------------

    def __repr__(self):
        return (
            f"ExperimentConfig(entry={self.entry_model},"
            f" stop={self.stop_mode}, target={self.target_mode},"
            f" rr={self.rr}, expiry={self.expiry})"
        )
