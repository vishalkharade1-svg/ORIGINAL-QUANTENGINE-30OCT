"""
====================================================

QuantEngine

Base Market Object

Parent class for market entities.

====================================================
"""

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class BaseMarketObject:
    """
    Base class for all market entities.
    """

    # -------------------------------------------------

    def to_dict(self):

        return asdict(self)

    # -------------------------------------------------

    def copy(self):

        return self.__class__(

            **self.to_dict()

        )

    # -------------------------------------------------

    def update(

        self,

        **kwargs,

    ):

        for key, value in kwargs.items():

            if hasattr(

                self,

                key,

            ):

                setattr(

                    self,

                    key,

                    value,

                )

        return self

    # -------------------------------------------------

    def __repr__(self):

        values = ", ".join(

            f"{k}={v!r}"

            for k, v in self.to_dict().items()

        )

        return (

            f"{self.__class__.__name__}"

            f"({values})"

        )