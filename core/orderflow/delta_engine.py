"""
====================================================

QuantEngine

Institutional Delta Engine

Coordinates:
    Provider
    Registry
    Analyzer
    State

====================================================
"""

from core.orderflow.delta import Delta
from core.orderflow.delta_analyser import DeltaAnalyzer
from core.orderflow.delta_registry import DeltaRegistry
from core.orderflow.delta_state import DeltaState


class DeltaEngine:

    def __init__(

        self,

        provider,

        lookback=10,

    ):

        self.provider = provider

        self.registry = DeltaRegistry()

        self.analyzer = DeltaAnalyzer(

            lookback=lookback,

        )

        self.state = DeltaState()

        self.cumulative_delta = 0.0

    # =================================================

    def process(

        self,

        source,

    ) -> Delta:

        delta = self.provider.calculate(

            source,

        )

        self.cumulative_delta += delta.delta

        delta.cumulative_delta = (

            self.cumulative_delta

        )

        if delta.candle_index == 0:

            delta.candle_index = len(

                self.registry.all()

            )

        self.registry.add(

            delta,

        )

        signal = self.analyzer.analyze(

            self.registry,

        )

        self.state.delta = delta

        self.state.signal = signal

        self.state.updated = True

        self.state.ready = True

        self.state.healthy = self.provider.healthy()

        self.state.source = self.provider.name

        self.state.confidence = delta.confidence

        if signal is not None:

            if signal.strong_buying:

                self.state.institutional_bias = "BULLISH"

            elif signal.strong_selling:

                self.state.institutional_bias = "BEARISH"

            else:

                self.state.institutional_bias = "NEUTRAL"

        self.state.update_statistics()

        return delta

    # =================================================

    def latest(self):

        return self.registry.latest()

    # -------------------------------------------------

    def previous(self):

        return self.registry.previous()

    # -------------------------------------------------

    def history(self):

        return self.registry.all()

    # -------------------------------------------------

    def signal(self):

        return self.state.signal

    # -------------------------------------------------

    def statistics(self):

        return self.state

    # =================================================

    def reset(self):

        self.cumulative_delta = 0.0

        self.registry.reset()

        self.state.reset()

        self.provider.reset()

    # -------------------------------------------------

    def session_reset(self):

        """
        Reset cumulative delta for a new session.
        """

        self.cumulative_delta = 0.0

    # -------------------------------------------------

    def shutdown(self):

        self.provider.shutdown()