"""
====================================================

Pipeline Diagnostics

Pipeline Native

Consumes:
    PipelineContext

====================================================
"""


class PipelineReport:

    def report(self, context):

        trend = context.trend
        regime = context.regime
        displacement = context.displacement
        fvg = context.fvgs
        order_blocks = context.order_blocks
        setups = context.decision

        print()

        print("=" * 70)
        print("PIPELINE SUMMARY")
        print("=" * 70)

        # -------------------------------------------------
        # Trend
        # -------------------------------------------------

        if trend:

            print()

            print("Trend Direction :", trend.direction)
            print("Trend Strength  :", round(trend.strength, 2))
            print("Trend Confidence:", round(trend.confidence, 2))

        # -------------------------------------------------
        # Regime
        # -------------------------------------------------

        if regime:

            print()

            print("=" * 70)
            print("REGIME ANALYSIS")
            print("=" * 70)

            print()

            print(f"Trend Score         : {regime.trend_score:>5}")
            print(f"Structure Score     : {regime.structure_score:>5}")
            print(f"Momentum Score      : {regime.momentum_score:>5}")
            print(f"Volatility Score    : {regime.volatility_score:>5}")
            print(f"Liquidity Score     : {regime.liquidity_score:>5}")
            print(f"Displacement Score  : {regime.displacement_score:>5}")
            print(f"FVG Score           : {regime.fvg_score:>5}")
            print(f"Order Block Score   : {regime.order_block_score:>5}")
            print(f"Breaker Score       : {regime.breaker_score:>5}")
            print(f"Mitigation Score    : {regime.mitigation_score:>5}")

            print()

            print("Final Score         :", round(regime.score, 2))
            print("Grade               :", regime.grade)
            print("Regime              :", regime.regime)

        # -------------------------------------------------
        # Scanner Summary
        # -------------------------------------------------

        print()

        print("=" * 70)
        print("SCANNER SUMMARY")
        print("=" * 70)

        if displacement:

            print()

            print("Displacements   :", displacement.count())
            print("Strong          :", len(displacement.strong()))

        if fvg:

            print()

            print("FVG             :", fvg.count())
            print("Active FVG      :", len(fvg.active()))
            print("Filled          :", len(fvg.filled()))

        if order_blocks:

            print()

            print("Order Blocks    :", order_blocks.count())
            print("Active          :", len(order_blocks.active()))
            print("Mitigated       :", len(order_blocks.mitigated()))

        # -------------------------------------------------
        # Trade Setups
        # -------------------------------------------------

        if setups:

            print()

            print("=" * 70)
            print("TRADE SETUPS")
            print("=" * 70)

            print()

            print("Accepted        :", setups.count())

            if hasattr(setups, "high_confidence"):

                print(
                    "High Confidence :",
                    len(setups.high_confidence())
                )

        print()