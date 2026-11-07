"""
====================================================

QuantEngine

Indexed Registry

Deliberately DISTINCT from core.common.base_registry.
BaseRegistry (list-backed, .remove(item) removes by
object identity). This registry is dict-backed and keyed
by object.id, supporting .get(id)/.remove(id) by id
rather than by object. SwingRegistry depends on the
id-based .remove(previous.id) semantics for swing
replacement -- do not merge this into BaseRegistry
without updating every .remove(x.id) call site to pass
the object instead of the id.

====================================================
"""

from __future__ import annotations

from typing import Dict
from typing import Generic
from typing import Iterable
from typing import Optional
from typing import TypeVar

from core.objects.market_object import MarketObject

T = TypeVar("T", bound=MarketObject)


class IndexedRegistry(Generic[T]):

    def __init__(self):

        self._objects: Dict[str, T] = {}

    # =====================================================
    # CRUD
    # =====================================================

    def add(self, obj: T):

        self._objects[obj.id] = obj

        return obj

    def get(

        self,

        object_id: str,

    ) -> Optional[T]:

        return self._objects.get(object_id)

    def remove(

        self,

        object_id: str,

    ):

        self._objects.pop(

            object_id,

            None,

        )

    # =====================================================
    # Collections
    # =====================================================

    def all(self) -> list[T]:

        return list(

            self._objects.values()

        )

    def active(self) -> list[T]:

        return [

            obj

            for obj in self._objects.values()

            if obj.active

        ]

    def archived(self) -> list[T]:

        return [

            obj

            for obj in self._objects.values()

            if obj.archived

        ]

    def invalidated(self) -> list[T]:

        return [

            obj

            for obj in self._objects.values()

            if obj.invalidated

        ]

    # =====================================================
    # Queries
    # =====================================================

    def best(self) -> Optional[T]:

        objects = self.active()

        if not objects:

            return None

        return max(

            objects,

            key=lambda x: x.score,

        )

    def top(

        self,

        n: int = 10,

    ) -> list[T]:

        return sorted(

            self.active(),

            key=lambda x: x.score,

            reverse=True,

        )[:n]

    def filter(

        self,

        tag: str,

    ) -> list[T]:

        return [

            obj

            for obj in self.active()

            if tag in obj.tags

        ]

    # =====================================================
    # Lifecycle
    # =====================================================

    def archive(

        self,

        object_id: str,

    ):

        obj = self.get(

            object_id,

        )

        if obj:

            obj.archive()

    def invalidate(

        self,

        object_id: str,

    ):

        obj = self.get(

            object_id,

        )

        if obj:

            obj.invalidate()

    # =====================================================
    # Maintenance
    # =====================================================

    def clear(self):

        self._objects.clear()

    def __len__(self):

        return len(

            self._objects

        )

    def __iter__(self) -> Iterable[T]:

        return iter(

            self._objects.values()

        )