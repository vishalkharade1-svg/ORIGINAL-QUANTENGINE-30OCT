"""
====================================================

QuantEngine

Base Scanner

Parent class for all scanners.

====================================================
"""

from abc import ABC, abstractmethod


class BaseScanner(ABC):

    def __init__(

        self,

        registry=None,

        name=None,

    ):

        self.name = (

            name

            or self.__class__.__name__

        )

        self.registry = registry

    # -------------------------------------------------

    @abstractmethod
    def scan(

        self,

        *args,

        **kwargs,

    ):
        """
        Scan market data and populate the registry.
        """

        raise NotImplementedError

    # -------------------------------------------------

    def reset(self):
        """
        Reset scanner state.
        """

        if self.registry is not None:

            self.registry.reset()

    # -------------------------------------------------

    def result(self):
        """
        Return scanner registry.
        """

        return self.registry

    # -------------------------------------------------

    def count(self):

        if self.registry is None:

            return 0

        return self.registry.count()

    # -------------------------------------------------

    def latest(self):

        if self.registry is None:

            return None

        return self.registry.latest()

    # -------------------------------------------------

    def clear(self):

        self.reset()

    # -------------------------------------------------

    def __len__(self):

        return self.count()

    # -------------------------------------------------

    def __repr__(self):

        return (

            f"{self.__class__.__name__}"

            f"(name='{self.name}', "

            f"items={self.count()})"

        )