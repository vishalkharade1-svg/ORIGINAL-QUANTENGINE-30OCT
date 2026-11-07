"""
====================================================

QuantEngine

Build : 2.11
Module : Warmup Engine

Loads historical candles and warms up indicators.

====================================================
"""

from config.settings import settings
from data.historical_loader import HistoricalLoader
from core.common.logging_config import get_logger

log = get_logger(__name__)


class WarmupEngine:

    def __init__(self, builder, indicators):

        self.builder = builder
        self.indicators = indicators

        self.loader = HistoricalLoader()

    def run(self):

        log.info("Loading historical candles...")

        data = self.loader.candles(settings.SYMBOLS[0])

        # Delta returns newest -> oldest
        candles = list(reversed(data["result"]))

        # Load into CandleBuilder
        self.builder.load_history(candles)

        log.info("Loaded %d candles.", self.builder.count())

        # Warm up indicators
        for candle in self.builder.history:

            self.indicators.on_new_candle(candle)

        log.info("Indicators warmed up.")

        self.loader.close()