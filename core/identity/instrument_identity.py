"""
====================================================

Canonical Setup Identity

Phase 6C: a namespaced identity that is built ONCE at
setup creation and then flows unchanged through the whole
execution chain (Setup -> Decision -> OrderIntent -> Pending
Order -> Position -> Trade -> Registry -> Logs -> Analytics).
The identity is a verbatim wrap of the pipeline's own
structural setup identity (setup_id); nothing about the
original is reinterpreted or rewritten.

Format
------

    {exchange}:{instrument_id}:{timeframe}:{direction}:{strategy}:{setup_id}

Example
-------

    delta:27:1m:BULLISH:BREAKOUT_CONTINUATION:OB-990

Because the unambiguous path separator is ":" and setup_ids
themselves never contain a colon, the LAST segment is always
recoverable verbatim from the full identity.

====================================================
"""

_SEGMENT_COUNT = 6

_VALID_DIRECTIONS = ("BULLISH", "BEARISH")


class IdentityError(ValueError):
    """
    Raised when a setup identity cannot be built or parsed
    (missing/invalid segments, malformed structure).
    """


def build_setup_identity(
    exchange,
    instrument_id,
    timeframe,
    direction,
    strategy,
    setup_id,
):
    """
    Build the canonical setup identity for one candidate.
    All segments must be non-empty; direction must be
    BULLISH or BEARISH. The setup_id suffix is wrapped
    verbatim and is the EXISTING pipeline structural
    identity -- never rewritten.
    """
    segments = {
        "exchange": exchange,
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "direction": direction,
        "strategy": strategy,
        "setup_id": setup_id,
    }

    for name, value in segments.items():
        if value is None or str(value).strip() == "":
            raise IdentityError(
                "cannot build setup identity: empty {} "
                "segment".format(name)
            )

    direction_value = str(direction).strip().upper()

    if direction_value not in _VALID_DIRECTIONS:
        raise IdentityError(
            "cannot build setup identity: direction {} "
            "not in {}".format(
                direction_value, _VALID_DIRECTIONS
            )
        )

    return ":".join(
        (
            str(exchange).strip(),
            str(instrument_id).strip(),
            str(timeframe).strip(),
            direction_value,
            str(strategy).strip(),
            str(setup_id).strip(),
        )
    )


def split_setup_identity(identity):
    """
    Round-trip parser: recover the six segments from a
    canonical setup identity, returning an OrderedDict-safe
    tuple in build order. The setup_id suffix is returned
    VERBATIM (split() drops all but the last part of a
    colon-free suffix without re-joining).
    """
    parts = str(identity).split(":")

    if len(parts) != _SEGMENT_COUNT:
        raise IdentityError(
            "malformed setup identity {}: expected {} "
            "segments, found {}".format(
                identity, _SEGMENT_COUNT, len(parts)
            )
        )

    exchange, instrument_id, timeframe, direction, strategy, setup_id = parts

    if str(direction).upper() not in _VALID_DIRECTIONS:
        raise IdentityError(
            "malformed setup identity {}: invalid "
            "direction {}".format(identity, direction)
        )

    return (
        exchange,
        instrument_id,
        timeframe,
        direction,
        strategy,
        setup_id,
    )