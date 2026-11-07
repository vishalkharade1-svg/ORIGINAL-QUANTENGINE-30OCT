"""
====================================================

QuantEngine

Institutional Delta Provider

Abstract interface for all Delta providers.

Replay:
    Estimates delta from OHLCV candles.

Live:
    Calculates delta from real trades.

====================================================
"""

from abc import ABC, abstractmethod

from core.orderflow.delta import Delta


class DeltaProvider(ABC):

    # ==================================================
    # Provider Information
    # ==================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider name.
        """
        raise NotImplementedError

    # --------------------------------------------------

    @property
    def live(self) -> bool:
        """
        True if this provider uses live trade data.
        """
        return False

    # ==================================================
    # Main API
    # ==================================================

    @abstractmethod
    def calculate(
        self,
        source,
    ) -> Delta:
        """
        Build a Delta object from the supplied source.
        """
        raise NotImplementedError

    # ==================================================
    # Optional Lifecycle Hooks
    # ==================================================

    def initialize(self):
        """
        Called once before the provider is used.
        """
        return None

    # --------------------------------------------------

    def shutdown(self):
        """
        Called when the provider is being stopped.
        """
        return None

    # --------------------------------------------------

    def reset(self):
        """
        Reset any internal provider state.
        """
        return None

    # ==================================================
    # Health
    # ==================================================

    def healthy(self) -> bool:
        """
        Returns whether the provider is operational.
        """
        return True