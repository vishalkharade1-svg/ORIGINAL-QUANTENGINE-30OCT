"""
====================================================

QuantEngine

Base Market Object

Every institutional object inherits from this.

====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from time import time

# Unique opaque ids: a monotonic counter is cheap (no uuid4
# formatting) and ids are only ever compared/held as opaque
# strings -- nothing parses the uuid format. Ids stay unique
# across the whole process lifetime, including reset/re-run.
_object_ids = count(1)


@dataclass(slots=True)
class MarketObject:

    # ==================================================
    # Identity
    # ==================================================

    id: str = field(
        default_factory=lambda: f"MKT-{next(_object_ids)}"
    )

    object_type: str = ""

    symbol: str = ""

    timeframe: str = ""

    # ==================================================
    # Lifecycle
    # ==================================================

    created_at: int = field(
        default_factory=lambda: int(time())
    )

    updated_at: int = field(
        default_factory=lambda: int(time())
    )

    active: bool = True

    invalidated: bool = False

    archived: bool = False

    # ==================================================
    # Institutional Scores
    # ==================================================

    score: float = 0.0

    confidence: float = 0.0

    quality: float = 0.0

    # ==================================================
    # Statistics
    # ==================================================

    touches: int = 0

    reactions: int = 0

    age: int = 0

    # ==================================================
    # Relationships
    # ==================================================

    parent: str | None = None

    children: list[str] = field(
        default_factory=list
    )

    tags: set[str] = field(
        default_factory=set
    )

    metadata: dict = field(
        default_factory=dict
    )

    # ==================================================
    # Helpers
    # ==================================================

    def touch(self):

        self.touches += 1

        self.updated_at = int(time())

    def react(self):

        self.reactions += 1

        self.updated_at = int(time())

    def invalidate(self):

        self.invalidated = True

        self.active = False

        self.updated_at = int(time())

    def archive(self):

        self.archived = True

        self.active = False

        self.updated_at = int(time())

    def activate(self):

        self.active = True

        self.invalidated = False

        self.archived = False

        self.updated_at = int(time())

    def add_tag(

        self,

        tag: str,

    ):

        self.tags.add(tag)

    def remove_tag(

        self,

        tag: str,

    ):

        self.tags.discard(tag)

    def set_score(

        self,

        score: float,

        confidence: float = 0.0,

        quality: float = 0.0,

    ):

        self.score = score

        self.confidence = confidence

        self.quality = quality

        self.updated_at = int(time())

    def update_age(

        self,

        current_timestamp: int,

    ):

        self.age = max(

            0,

            current_timestamp - self.created_at,

        )