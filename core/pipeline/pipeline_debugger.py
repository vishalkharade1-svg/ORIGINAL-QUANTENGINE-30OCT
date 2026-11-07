"""
====================================================

QuantEngine

Institutional Pipeline Debugger

====================================================
"""

from pprint import pprint


class PipelineDebugger:

    def __init__(self):
        self.enabled = True

    # -------------------------------------------------

    def dump(self, context):

        if not self.enabled:
            return

        print()
        print("=" * 80)
        print(f"PIPELINE #{context.current_index}")
        print("=" * 80)

        self._market(context)
        self._indicators(context)
        self._trend(context)
        self._structure(context)
        self._liquidity(context)
        self._displacement(context)
        self._fvg(context)
        self._order_blocks(context)
        self._regime(context)
        self._trade_setup(context)
        self._decision(context)

    # -------------------------------------------------

    def _market(self, context):

        print("\nMARKET")

        print(f"Price        : {context.market.mark_price}")
        print(f"Bars         : {context.candle_count}")

    # -------------------------------------------------

    def _indicators(self, context):

        print("\nINDICATORS")

        cache = context.indicators

        if cache is None:
            print("Indicator Cache : NONE")
            return

        print(f"Cache ID       : {id(cache)}")
        print(f"Cache Type     : {type(cache).__name__}")

        if not hasattr(cache, "data"):
            print("ERROR : Not an IndicatorCache")
            return

        print(f"Keys           : {list(cache.data.keys())}")
        print()

        names = [
            "EMA_20",
            "EMA_50",
            "EMA_200",
            "ATR_14",
            "ADX_14",
            "RSI_14",
        ]

        for name in names:

            values = cache.get(name)

            if values is None:
                print(f"{name:10} : MISSING")
                continue

            latest = values[-1] if values else None

            print(
                f"{name:10} : "
                f"{latest} "
                f"(len={len(values)})"
            )

    # -------------------------------------------------

    def _trend(self, context):

        print("\nTREND")

        trend = context.trend

        if trend is None:
            print("None")
            return

        attrs = [
            "direction",
            "score",
            "regime",
            "ema_alignment",
            "price_above_ema20",
            "price_above_ema50",
            "price_above_ema200",
            "adx_confirmed",
            "momentum",
        ]

        for attr in attrs:

            if hasattr(trend, attr):
                print(f"{attr:20}: {getattr(trend, attr)}")

    # -------------------------------------------------

    def _structure(self, context):

        print("\nMARKET STRUCTURE")

        s = context.market_structure

        if s is None:
            print("None")
            return

        for attr in ["bos", "choch", "trend"]:

            if hasattr(s, attr):
                print(f"{attr:20}: {getattr(s, attr)}")

    # -------------------------------------------------

    def _liquidity(self, context):

        print("\nLIQUIDITY")

        pools = context.liquidity

        if pools is None:
            print("None")
            return

        try:
            print("Pools :", len(pools))
        except Exception:
            print(type(pools))

    # -------------------------------------------------

    def _displacement(self, context):

        print("\nDISPLACEMENT")

        registry = context.displacement

        if registry is None:
            print("None")
            return

        if hasattr(registry, "strong"):
            print("Strong :", len(registry.strong()))
        else:
            print(type(registry))

    # -------------------------------------------------

    def _fvg(self, context):

        print("\nFVG")

        registry = context.fvgs

        if registry is None:
            print("None")
            return

        if hasattr(registry, "active"):
            print("Active :", len(registry.active()))
        else:
            print(type(registry))

    # -------------------------------------------------

    def _order_blocks(self, context):

        print("\nORDER BLOCKS")

        registry = context.order_blocks

        if registry is None:
            print("None")
            return

        if hasattr(registry, "active"):
            print("Active :", len(registry.active()))
        else:
            print(type(registry))

    # -------------------------------------------------

    def _regime(self, context):

        print("\nREGIME")

        regime = context.regime

        if regime is None:
            print("None")
            return

        if hasattr(regime, "regime"):
            print("Regime :", regime.regime)

        if hasattr(regime, "score"):
            print("Score  :", regime.score)

    # -------------------------------------------------

    def _trade_setup(self, context):

        print("\nTRADE SETUPS")

        setups = context.trade_setups

        if setups is None:
            print("None")
            return

        try:
            print("Count :", len(setups))
        except Exception:
            print(type(setups))

    # -------------------------------------------------

    def _decision(self, context):

        print("\nDECISION")

        registry = context.decision

        if registry is None:
            print("None")
            return

        if hasattr(registry, "__len__"):
            print("Accepted :", len(registry))

        if hasattr(registry, "all"):
            pprint(registry.all())

        elif isinstance(registry, list):
            pprint(registry)