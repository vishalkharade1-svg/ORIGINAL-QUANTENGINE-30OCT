"""
====================================================

Historical Storage

Parquet persistence layer.

====================================================
"""

from pathlib import Path

import pandas as pd


class HistoryStorage:

    ROOT = Path("data/history")

    def __init__(self):

        self.ROOT.mkdir(

            parents=True,

            exist_ok=True,

        )

    # -------------------------------------------------

    def _path(

        self,

        symbol,

        timeframe,

    ):

        folder = self.ROOT / symbol

        folder.mkdir(

            parents=True,

            exist_ok=True,

        )

        return folder / f"{timeframe}.parquet"

    # -------------------------------------------------

    def save(

        self,

        symbol,

        timeframe,

        candles,

    ):

        df = pd.DataFrame(

            [

                {

                    "timestamp": c.timestamp,

                    "open": c.open,

                    "high": c.high,

                    "low": c.low,

                    "close": c.close,

                    "volume": c.volume,

                }

                for c in candles

            ]

        )

        # ---------------------------------------------
        # Remove duplicate candles
        # ---------------------------------------------

        df = df.drop_duplicates(

            subset="timestamp",

            keep="last",

        )

        # ---------------------------------------------
        # Always store oldest → newest
        # ---------------------------------------------

        df = df.sort_values(

            "timestamp"

        ).reset_index(

            drop=True

        )

        df.to_parquet(

            self._path(

                symbol,

                timeframe,

            ),

            index=False,

        )

    # -------------------------------------------------

    def load(

        self,

        symbol,

        timeframe,

    ):

        path = self._path(

            symbol,

            timeframe,

        )

        if not path.exists():

            return None

        df = pd.read_parquet(path)

        df = df.sort_values(

            "timestamp"

        ).reset_index(

            drop=True

        )

        return df

    # -------------------------------------------------

    def exists(

        self,

        symbol,

        timeframe,

    ):

        return self._path(

            symbol,

            timeframe,

        ).exists()

    # -------------------------------------------------

    def delete(

        self,

        symbol,

        timeframe,

    ):

        path = self._path(

            symbol,

            timeframe,

        )

        if path.exists():

            path.unlink()