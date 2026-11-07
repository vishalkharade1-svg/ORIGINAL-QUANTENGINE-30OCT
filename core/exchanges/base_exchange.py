"""
====================================================

Base Exchange

====================================================
"""

from abc import ABC, abstractmethod


class BaseExchange(ABC):

    @abstractmethod
    def get_products(self):
        pass

    @abstractmethod
    def get_balance(self):
        pass

    @abstractmethod
    def get_positions(self):
        pass

    @abstractmethod
    def place_order(self, order):
        pass

    @abstractmethod
    def cancel_order(self, order_id):
        pass

    @abstractmethod
    def get_order(self, order_id):
        pass