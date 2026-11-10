"""Research-only SENSEX expiry-squeeze data capture primitives.

This package records observations. It does not generate orders, connect to a
broker, or certify a trading strategy.
"""

from .recorder import (
    CaptureLimitError,
    CorruptJournalError,
    ExpirySqueezeRecorder,
    RecorderError,
    candidate_identity,
)

__all__ = [
    "CaptureLimitError",
    "CorruptJournalError",
    "ExpirySqueezeRecorder",
    "RecorderError",
    "candidate_identity",
]
