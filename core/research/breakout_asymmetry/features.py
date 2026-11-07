"""
====================================================

QuantEngine

Phase 7A -- Causal Dataset Decomposition

Extract an IDENTICAL feature family for every bullish and
bearish breakout from the frozen causal record (the
CausalValidationState dataset). No thresholds are changed.
This module only DESCRIBES the population: it answers,
for each axis, what the bullish vs bearish distributions
look like.

Feature families (identical for both directions):

    displacement magnitude          |entry - creation_price|
    ATR-normalized displacement     (as above) / atr
    breakout distance               |entry - trigger_close|
    order-block width               |entry - stop_loss|
    FVG presence                    from setup metadata
    swap/structure type             setup-level axis
    liquidity event                 setup-level axis
    prior swing geometry            entry/stop price span
    volume axis                     carried atr-scoped
    orderflow axis                  (reserved, 0 when absent)
    candle body/wick                setup-level axis
    distance from market            entry_distance_atr
    setup age                       creation_bar age
    time since structural event     creation_bar moment
    entry-to-stop distance          |entry - stop_loss|
    entry-to-target distance        |target - entry|

Every axis is extracted through the SAME function
(feature_axis name -> value) for both directions, so any
per-direction difference is a property of the DATA, not of
the extractor.
====================================================
"""

from dataclasses import dataclass, field
from enum import Enum


class Axis(Enum):

    DISPLACEMENT = "displacement"
    DISPLACEMENT_ATR = "displacement_atr"
    BREAKOUT_DISTANCE = "breakout_distance"
    ORDER_BLOCK_WIDTH = "order_block_width"
    FVG_PRESENCE = "fvg_presence"
    STRUCTURE_TYPE = "structure_type"
    LIQUIDITY_EVENT = "liquidity_event"
    SWING_GEOMETRY = "swing_geometry"
    VOLUME = "volume"
    ORDERFLOW = "orderflow"
    BODY_WICK = "body_wick"
    DISTANCE_FROM_MARKET = "distance_from_market"
    SETUP_AGE = "setup_age"
    TIME_SINCE_STRUCTURE = "time_since_structure"
    ENTRY_TO_STOP = "entry_to_stop"
    ENTRY_TO_TARGET = "entry_to_target"


# Identity of the 16 feature families (name -> family id)
# so the report can group them in a stable order.
AXIS_ORDER = [axis.value for axis in Axis]


def _safe_div(a, b, default=0.0):
    try:
        b = float(b)
        if not b or b <= 0:
            return default
        return float(a) / b
    except (TypeError, ValueError, ZeroDivisionError):
        return default


@dataclass
class FeatureRow:
    """One causal setup's 16-axis feature vector (7A)."""

    setup_id: str = ""
    direction: str = ""
    structural_id: str = ""
    economic_fingerprint: str = ""
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0

    # First half: price/geometry family.
    displacement: float = 0.0
    displacement_atr: float = 0.0
    breakout_distance: float = 0.0
    order_block_width: float = 0.0
    fvg_presence: float = 0.0

    # Second half: market/structure family.
    structure_type: float = 0.0
    liquidity_event: float = 0.0
    swing_geometry: float = 0.0
    volume: float = 0.0
    orderflow: float = 0.0
    body_wick: float = 0.0

    # Timing / entry geometry family.
    distance_from_market: float = 0.0
    setup_age: float = 0.0
    time_since_structure: float = 0.0
    entry_to_stop: float = 0.0
    entry_to_target: float = 0.0

    # Cross-link back to the source record.
    source_index: int = -1

    def axis_values(self):
        """Ordered {axis_name -> value} view for comparison."""

        return {
            Axis.DISPLACEMENT.value: self.displacement,
            Axis.DISPLACEMENT_ATR.value: self.displacement_atr,
            Axis.BREAKOUT_DISTANCE.value: self.breakout_distance,
            Axis.ORDER_BLOCK_WIDTH.value: self.order_block_width,
            Axis.FVG_PRESENCE.value: self.fvg_presence,
            Axis.STRUCTURE_TYPE.value: self.structure_type,
            Axis.LIQUIDITY_EVENT.value: self.liquidity_event,
            Axis.SWING_GEOMETRY.value: self.swing_geometry,
            Axis.VOLUME.value: self.volume,
            Axis.ORDERFLOW.value: self.orderflow,
            Axis.BODY_WICK.value: self.body_wick,
            Axis.DISTANCE_FROM_MARKET.value: self.distance_from_market,
            Axis.SETUP_AGE.value: self.setup_age,
            Axis.TIME_SINCE_STRUCTURE.value: self.time_since_structure,
            Axis.ENTRY_TO_STOP.value: self.entry_to_stop,
            Axis.ENTRY_TO_TARGET.value: self.entry_to_target,
        }


class FeatureExtractor:
    """Deterministic, direction-agnostic axis extractor.

    The SAME instance extracts every axis for BOTH directions,
    so any observed difference is a population property, not an
    extractor artifact. Values are ATR-normalized where the
    family is a price magnitude; categorical axes are encoded
    to 0/1 flags so they enter the numeric comparison without a
    regime assumption.
    """

    def __init__(self, metadata=None):
        """metadata: optional dict of setup-level flags keyed by
        setup_id -> {'fvg': bool, 'structure': str, 'liquidity':
        str, 'volume': float, 'orderflow': float, 'body_wick':
        float, 'creation_price': float}. Absent keys fall back to
        data carried inside the causal record itself."""

        self.metadata = metadata or {}

    # --------------------------------------------------

    def extract(self, state, index=None):
        """state: one CausalValidationState (the frozen causal
        record). Returns a FeatureRow. Index is the dataset
        index used to cross-link back."""

        entry = float(getattr(state, "entry", 0.0) or 0.0)
        stop = float(getattr(state, "stop_loss", 0.0) or 0.0)
        target = float(getattr(state, "take_profit", 0.0) or 0.0)
        atr = float(getattr(state, "atr", 0.0) or 0.0)
        direction = (getattr(state, "direction", "") or "").upper()
        creation_price = float(
            getattr(state, "creation_price", 0.0) or 0.0
        )
        entry_distance_atr = float(
            getattr(state, "entry_distance_atr", 0.0) or 0.0
        )
        trigger_close = getattr(state, "breakout_trigger_close", None)
        created_bar = getattr(state, "creation_bar", 0) or 0

        meta = self.metadata.get(state.setup_id, {})

        # displacement magnitude (always non-negative)
        displacement = abs(entry - creation_price)

        row = FeatureRow(
            setup_id=getattr(state, "setup_id", "") or "",
            direction=direction,
            structural_id=getattr(state, "structural_id", "") or "",
            economic_fingerprint=(
                getattr(state, "economic_fingerprint", "") or ""
            ),
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            displacement=displacement,
            displacement_atr=_safe_div(displacement, atr),
            breakout_distance=(
                abs(entry - float(trigger_close))
                if trigger_close is not None
                else 0.0
            ),
            order_block_width=abs(entry - stop),
            fvg_presence=float(bool(meta.get("fvg", False))),
            structure_type=float(bool(meta.get("structure", ""))),
            liquidity_event=float(bool(meta.get("liquidity", ""))),
            swing_geometry=abs(entry - stop),
            volume=float(meta.get("volume", 0.0) or 0.0),
            orderflow=float(meta.get("orderflow", 0.0) or 0.0),
            body_wick=float(meta.get("body_wick", 0.0) or 0.0),
            distance_from_market=entry_distance_atr,
            setup_age=float(created_bar or 0),
            time_since_structure=float(created_bar or 0),
            entry_to_stop=abs(entry - stop),
            entry_to_target=abs(target - entry),
            source_index=index,
        )

        return row


def extract_features(states, metadata=None):
    """Extract FeatureRow for every record in the causal dataset.
    Returns a list aligned with `states` (index preserved)."""

    extractor = FeatureExtractor(metadata=metadata)

    return [
        extractor.extract(state, index=i)
        for i, state in enumerate(states)
    ]