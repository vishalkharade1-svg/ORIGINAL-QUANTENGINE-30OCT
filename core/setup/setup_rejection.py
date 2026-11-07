"""
====================================================

Trade Setup Rejection

====================================================
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SetupRejection:

    direction: str = ""

    reasons: list[str] = field(default_factory=list)

    candidate: Any = None

    def add(self, reason: str):

        self.reasons.append(reason)