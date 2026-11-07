"""
====================================================

QuantEngine

Market Event Bus

====================================================
"""

from core.events.event_dispatcher import EventDispatcher


class EventBus:

    def __init__(self):

        self._subscribers = {}

        self._dispatcher = EventDispatcher()

    # -------------------------------------------------

    def subscribe(

        self,

        event_type,

        callback,

    ):

        self._subscribers.setdefault(

            event_type,

            []

        ).append(callback)

    # -------------------------------------------------

    def unsubscribe(

        self,

        event_type,

        callback,

    ):

        callbacks = self._subscribers.get(

            event_type,

            []

        )

        if callback in callbacks:

            callbacks.remove(callback)

    # -------------------------------------------------

    def publish(

        self,

        event,

    ):

        self._dispatcher.push(event)

        self.dispatch()

    # -------------------------------------------------

    def dispatch(self):

        while not self._dispatcher.empty():

            event = self._dispatcher.pop()

            callbacks = self._subscribers.get(

                event.event_type,

                [],

            )

            for callback in callbacks:

                callback(event)

    # -------------------------------------------------

    def clear(self):

        self._subscribers.clear()

        self._dispatcher.clear()