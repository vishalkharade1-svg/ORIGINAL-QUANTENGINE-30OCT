"""
====================================================

Compatibility Registry

Legacy wrapper around BaseRegistry

====================================================
"""

from core.common.base_registry import BaseRegistry


class Registry(BaseRegistry):
    """
    Temporary compatibility layer.

    Existing registries can continue inheriting from
    Registry until the migration is complete.

    This class will be removed after Sprint 36.5.
    """

    pass