"""Backward-compatible import alias for the canonical RealTimeEngine.

Phase 208 folds the optional paper market-data gate into RealTimeEngine.
This module remains only so older imports continue to work; it defines no
second engine implementation.
"""
from core.runtime.realtime_engine import RealTimeEngine

GatedRealTimeEngine = RealTimeEngine

__all__ = ["GatedRealTimeEngine"]
