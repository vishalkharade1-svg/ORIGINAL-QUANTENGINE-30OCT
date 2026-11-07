"""
====================================================

Delta Products Downloader

====================================================
"""

from core.exchanges.delta.delta_rest import DeltaREST


class DeltaProducts:

    def __init__(self, rest=None):

        # Same environment-separation seam as DeltaHistory: an
        # explicit transport may be injected; default preserves
        # the legacy endpoint for existing callers.
        self.rest = rest if rest is not None else DeltaREST()

    # -------------------------------------------------

    def download(self):

        return self.rest.get(

            "/v2/products"

        )