"""
====================================================

Canonical Instrument/Setup Identity

====================================================
"""

from core.identity.instrument_identity import (
    IdentityError,
    build_setup_identity,
    split_setup_identity,
)

__all__ = [
    "IdentityError",
    "build_setup_identity",
    "split_setup_identity",
]