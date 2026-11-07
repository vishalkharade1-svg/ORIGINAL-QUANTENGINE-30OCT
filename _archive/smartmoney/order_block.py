from dataclasses import dataclass


@dataclass
class OrderBlock:

    direction: str

    high: float

    low: float

    timestamp: int

    active: bool = True

    mitigated: bool = False

    invalidated: bool = False

    mitigation_timestamp: int = 0

    invalidation_timestamp: int = 0

    touches: int = 0