"""
====================================================

QuantEngine

Base Registry

Parent class for all registries.

====================================================
"""


class BaseRegistry:

    def __init__(self):

        self._items = []

    # -------------------------------------------------
    # Basic Operations
    # -------------------------------------------------

    def add(

        self,

        item,

    ):

        self._items.append(item)

    # -------------------------------------------------

    def remove(

        self,

        item,

    ):

        if item in self._items:

            self._items.remove(item)

    # -------------------------------------------------

    def clear(self):

        self._items.clear()

    # -------------------------------------------------

    def reset(self):

        self.clear()

    # -------------------------------------------------
    # Accessors
    # -------------------------------------------------

    def all(self):

        return self._items

    # -------------------------------------------------

    def count(self):

        return len(self._items)

    # -------------------------------------------------

    def first(self):

        if not self._items:

            return None

        return self._items[0]

    # -------------------------------------------------

    def latest(self):

        if not self._items:

            return None

        return self._items[-1]

    # -------------------------------------------------

    def previous(self):

        if len(self._items) < 2:

            return None

        return self._items[-2]

    # -------------------------------------------------

    def last(

        self,

        count=1,

    ):

        if count <= 0:

            return []

        return self._items[-count:]

    # -------------------------------------------------
    # Filters
    # -------------------------------------------------

    def active(self):

        return [

            item

            for item in self._items

            if getattr(

                item,

                "active",

                False,

            )

        ]

    # -------------------------------------------------

    def inactive(self):

        return [

            item

            for item in self._items

            if not getattr(

                item,

                "active",

                False,

            )

        ]

    # -------------------------------------------------
    # Python Helpers
    # -------------------------------------------------

    def __len__(self):

        return len(self._items)

    # -------------------------------------------------

    def __iter__(self):

        return iter(self._items)

    # -------------------------------------------------

    def __getitem__(

        self,

        index,

    ):

        return self._items[index]

    # -------------------------------------------------

    def __contains__(

        self,

        item,

    ):

        return item in self._items

    # -------------------------------------------------

    def __bool__(self):

        return bool(self._items)

    # -------------------------------------------------

    def __repr__(self):

        return (

            f"{self.__class__.__name__}"

            f"(count={len(self._items)})"

        )