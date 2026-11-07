from dataclasses import dataclass


@dataclass
class TradeSignal:

    direction: str

    score: int

    confidence: str

    reasons: list