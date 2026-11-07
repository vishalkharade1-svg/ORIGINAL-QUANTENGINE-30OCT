"""
====================================================

Institutional Confluence

====================================================
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Confluence:
    """
    Institutional Confluence Result.

    Represents the combined evidence produced by
    the Institutional Pipeline.
    """

    # -------------------------------------------------
    # Overall
    # -------------------------------------------------

    score: float = 0.0

    confidence: float = 0.0

    quality: float = 0.0

    # -------------------------------------------------
    # Direction
    # -------------------------------------------------

    bullish: bool = False

    bearish: bool = False

    # -------------------------------------------------
    # Diagnostics
    # -------------------------------------------------

    reasons: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    # -------------------------------------------------
    # Future Institutional Contributors
    # -------------------------------------------------

    contributors: dict[str, float] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # -------------------------------------------------

    def add_reason(self, reason: str):

        if reason not in self.reasons:
            self.reasons.append(reason)

    # -------------------------------------------------

    def add_warning(self, warning: str):

        if warning not in self.warnings:
            self.warnings.append(warning)

    # -------------------------------------------------

    def add_contributor(
        self,
        name: str,
        score: float,
    ):

        self.contributors[name] = score

    # -------------------------------------------------

    def normalize(self):

        self.score = max(
            0.0,
            min(100.0, self.score),
        )

        self.confidence = max(
            0.0,
            min(100.0, self.confidence),
        )

        self.quality = max(
            0.0,
            min(100.0, self.quality),
        )

        return self