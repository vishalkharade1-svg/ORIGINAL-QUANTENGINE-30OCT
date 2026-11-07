from dataclasses import dataclass


@dataclass
class TimeframeSignal:

    timeframe: str

    direction: str

    score: int

    confidence: str