"""
====================================================

QuantEngine

Canonical Base Engine

Parent class for every institutional engine.

====================================================
"""

from abc import ABC, abstractmethod


class BaseEngine(ABC):

    # -------------------------------------------------
    # Pipeline Metadata
    # -------------------------------------------------

    priority = 100

    dependencies = []

    enabled = True

    # -------------------------------------------------

    def __init__(self):

        self.name = self.__class__.__name__

        self.initialized = False

    # -------------------------------------------------
    # Lifecycle
    # -------------------------------------------------

    def initialize(
        self,
        context=None,
    ):
        """
        Optional startup hook.
        """

        self.initialized = True

    # -------------------------------------------------

    def validate(
        self,
        context,
    ):
        """
        Optional validation before processing.
        Return False to skip this engine.
        """

        return True

    # -------------------------------------------------

    @abstractmethod
    def analyze(
        self,
        context,
    ):
        """
        Engine implementation.

        Every institutional engine implements
        analyze(context).

        process() calls this automatically.
        """

        raise NotImplementedError

    # -------------------------------------------------

    def process(
        self,
        context,
    ):
        """
        Standard pipeline entry.

        Do not override unless absolutely necessary.
        """

        if not self.enabled:
            return None

        if not self.validate(context):
            return None

        return self.analyze(context)

    # -------------------------------------------------

    def reset(
        self,
    ):
        """
        Reset engine state.
        """

        pass

    # -------------------------------------------------

    def shutdown(
        self,
    ):
        """
        Optional cleanup.
        """

        pass

    # -------------------------------------------------

    @property
    def ready(self):

        return self.enabled and self.initialized

    # -------------------------------------------------

    def __repr__(self):

        return (
            f"<{self.name} "
            f"priority={self.priority} "
            f"enabled={self.enabled}>"
        )