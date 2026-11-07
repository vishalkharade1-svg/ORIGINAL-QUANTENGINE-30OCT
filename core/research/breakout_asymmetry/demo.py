"""
====================================================

QuantEngine

Phase 7 -- Breakout Asymmetry research demo (isolated path)

Runs the complete bullish-vs-bearish BREAKOUT asymmetry
research chain (7A features, 7B outcomes, 7C origins,
7D counterfactual, 7E evidence-led hypothesis) on a SYNTHETIC
causal dataset that mirrors the user-reported asymmetry
(bearish strong: PF>3 + positive expectancy + small MAE;
bullish weak: high win rate but negative expectancy + deep
MAE).

This is the ISOLATED research path entry point: it never
touches the frozen production pipeline, changes no threshold,
and produces only evidence. To run against REAL captured
causal data, call build_report() with the CausalValidator's
CausalValidationState records (load_dataset() accepts a JSON
path or the native list).

Usage:
    python -m core.research.breakout_asymmetry.demo
====================================================
"""

from core.setup.causal_validation import CausalValidationState
from core.research.breakout_asymmetry import build_report


def _state(direction, setup_id, entry, stop, target, atr,
           creation_price, resolved, conservative, sl_hit, tp_hit,
           r_multiple, mae_atr, mfe_atr, entry_distance_atr=0.0):

    return CausalValidationState(
        setup_id=setup_id,
        structural_id=setup_id,
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        atr=atr,
        creation_bar=0,
        creation_price=creation_price,
        entry_distance_atr=entry_distance_atr,
        breakout_triggered=True,
        breakout_trigger_bar=1,
        breakout_trigger_close=None,
        breakout_entry_bar=2,
        breakout_entry_price=entry,
        breakout_entered=True,
        breakout_causally_executable=True,
        breakout_resolved=resolved,
        breakout_conservative=conservative,
        breakout_sl_hit=sl_hit,
        breakout_tp_hit=tp_hit,
        breakout_ambiguous=False,
        breakout_mae=0.0,
        breakout_mfe=0.0,
        breakout_mae_atr=mae_atr,
        breakout_mfe_atr=mfe_atr,
        breakout_r_multiple=r_multiple,
    )


def mirror_reported_bearish(n=40):
    """~86% win bearish population, wins +~1.6-1.8R, small MAE."""

    states = []

    for i in range(n):

        win = (i % 7) != 0

        risk = 10.0
        reward = 15.0 + (i % 4)

        states.append(
            _state(
                "BEARISH",
                f"BEARQ-{i}",
                100.0,
                110.0,
                100.0 - reward,
                10.0,
                102.0,
                "WIN" if win else "LOSS",
                "WIN" if win else "LOSS",
                not win,
                win,
                (reward / risk) if win else -1.0,
                0.3 if win else 0.4,
                (0.9 if win else 0.2),
                0.5,
            )
        )

    return states


def mirror_reported_bullish(n=30):
    """~75% win bullish population, wins +0.2R, losses -1R,
    deep adverse excursion -> negative expectancy, PF < 1."""

    states = []

    for i in range(n):

        win = (i % 4) != 0

        risk = 10.0
        reward = 2.0

        states.append(
            _state(
                "BULLISH",
                f"BULLQ-{i}",
                100.0,
                90.0,
                102.0,
                10.0,
                99.0,
                "WIN" if win else "LOSS",
                "WIN" if win else "LOSS",
                not win,
                win,
                (reward / risk) if win else -1.0,
                4.0 if win else 0.5,
                0.2,
                3.0,
            )
        )

    return states


def main():

    states = mirror_reported_bullish() + mirror_reported_bearish()

    report = build_report(states)

    print(report.summary())
    print()

    dump_path = __import__("os").path.join(
        __import__("os").path.dirname(__file__),
        "results",
        "phase7_report.json",
    )

    report.dump(dump_path)

    print(f"report dumped -> {dump_path}")


if __name__ == "__main__":

    main()