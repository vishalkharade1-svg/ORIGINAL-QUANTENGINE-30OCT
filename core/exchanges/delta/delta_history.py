"""
====================================================

Delta Historical Downloader

====================================================
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json

from core.exchanges.delta.delta_rest import DeltaREST


class DeltaHistory:

    def __init__(self, rest=None):

        # Environment separation: an explicit transport (e.g. a
        # Testnet-pointed DeltaREST) may be injected; the default
        # preserves the legacy endpoint so existing callers are
        # behavior-neutral. Attribute assignment (history.rest = …)
        # remains supported as before.
        self.rest = rest if rest is not None else DeltaREST()

    # -------------------------------------------------

    def gap_candles(self, symbol, resolution, after_ts, before_ts):
        """Fetch only the historical buckets strictly inside a live-feed gap."""
        from data.candle_builder import TIMEFRAME_SECONDS
        window = int(TIMEFRAME_SECONDS.get(resolution, 0))
        if window <= 0:
            raise ValueError("unsupported resolution")
        after = int(after_ts)
        before = int(before_ts)
        if before <= after + window:
            return []
        return self.candles(
            symbol, resolution=resolution,
            start=after + window, end=before - window, days=1,
        )

    def funding_rates(self, symbol, resolution="1h", start=None, end=None, days=7):
        """Fetch Delta funding-rate history as explicit research evidence.

        Delta exposes funding history through the public historical-candles
        endpoint using ``FUNDING:<symbol>``.  This method deliberately
        returns validated timestamp/rate records instead of pretending the
        funding series is ordinary OHLCV candles.
        """
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol is required")
        if resolution not in {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d"}:
            raise ValueError("unsupported funding resolution")
        if end is None:
            end = int(datetime.now(timezone.utc).timestamp())
        if start is None:
            start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        if int(end) <= int(start):
            raise ValueError("funding end must be after start")
        response = self.rest.get(
            "/v2/history/candles",
            params={
                "symbol": "FUNDING:%s" % str(symbol).strip(),
                "resolution": resolution,
                "start": int(start),
                "end": int(end),
            },
        )
        rows = response.get("result") if isinstance(response, dict) else response
        if not isinstance(rows, list):
            raise ValueError("Delta funding response has no result list")
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                ts = int(row["time"])
                # Delta's funding-history candle response represents the
                # funding value in the candle close field.  Accept an
                # explicit rate field too for forward-compatible fixtures.
                raw_rate = row.get("rate", row.get("close"))
                rate = float(raw_rate)
            except (KeyError, TypeError, ValueError):
                continue
            if ts <= 0 or rate != rate or rate == float("inf") or rate == float("-inf"):
                continue
            out.append({"time": ts, "rate": rate})
        out.sort(key=lambda item: item["time"])
        deduped = []
        seen = set()
        for item in out:
            if item["time"] in seen:
                continue
            seen.add(item["time"])
            deduped.append(item)
        return deduped

    def funding_evidence(self, symbol, resolution="1h", start=None, end=None, days=7):
        """Fetch strict, fingerprinted Delta funding evidence.

        Unlike the compatibility ``funding_rates`` helper, this path never
        silently deduplicates provider rows. Duplicate settlement timestamps,
        malformed rows, or an empty result are evidence failures. The returned
        fingerprint is over the canonical normalized evidence plus request
        identity, so an OOS artifact can bind to the exact funding boundary.
        """
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol is required")
        if resolution not in {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d"}:
            raise ValueError("unsupported funding resolution")
        if end is None:
            end = int(datetime.now(timezone.utc).timestamp())
        if start is None:
            start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        if int(end) <= int(start):
            raise ValueError("funding end must be after start")
        request = {"symbol": "FUNDING:%s" % str(symbol).strip(),
                   "resolution": resolution, "start": int(start), "end": int(end)}
        response = self.rest.get("/v2/history/candles", params=request)
        rows = response.get("result") if isinstance(response, dict) else response
        if not isinstance(rows, list) or not rows:
            raise ValueError("Delta funding response has no non-empty result list")
        out = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Delta funding response contains non-object row")
            try:
                ts = int(row["time"])
                raw_rate = row.get("rate", row.get("close"))
                rate = float(raw_rate)
            except (KeyError, TypeError, ValueError):
                raise ValueError("Delta funding response contains malformed row")
            if ts <= 0 or rate != rate or rate in (float("inf"), float("-inf")):
                raise ValueError("Delta funding response contains non-finite row")
            if ts in seen:
                raise ValueError("Delta funding response contains duplicate settlement timestamp")
            seen.add(ts)
            out.append({"time": ts, "rate": rate})
        out.sort(key=lambda item: item["time"])
        canonical = {"request": request, "events": out}
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "venue": "delta", "endpoint": "/v2/history/candles",
            "request": request, "events": out,
            "event_count": len(out), "sha256": fingerprint,
        }

    def orderbook_evidence(self, symbol, depth=None):
        """Fetch and strictly validate one public Delta L2 orderbook snapshot.

        This is venue market-state evidence only; it is not historical fill or
        realized-slippage evidence.
        """
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol is required")
        params = {}
        if depth is not None:
            depth_i = int(depth)
            if depth_i <= 0:
                raise ValueError("depth must be positive")
            params["depth"] = depth_i
        response = self.rest.get("/v2/l2orderbook/%s" % str(symbol).strip(), params=params)
        from research.economics.orderbook_evidence import normalize_orderbook, evidence_sha256
        normalized = normalize_orderbook(response, symbol=str(symbol).strip())
        request = {"symbol": str(symbol).strip(), "endpoint": "/v2/l2orderbook/{symbol}", "depth": params.get("depth")}
        return {
            "venue": "delta", "endpoint": request["endpoint"], "request": request,
            "result": normalized, "sha256": evidence_sha256(request, normalized),
        }

    def candles(

        self,

        symbol,

        resolution="1m",

        start=None,

        end=None,

        days=7,

    ):

        from core.history.candle_mapper import CandleMapper

        # ---------------------------------------------
        # Automatically create timestamps
        # ---------------------------------------------

        if end is None:

            end = int(datetime.now(timezone.utc).timestamp())

        if start is None:

            start = int(

                (

                    datetime.now(timezone.utc)

                    - timedelta(days=days)

                ).timestamp()

            )

        params = {

            "symbol": symbol,

            "resolution": resolution,

            "start": start,

            "end": end,

        }

    # ---------------------------------------------
    # Download candles
    # ---------------------------------------------

        response = self.rest.get(

            "/v2/history/candles",

            params=params,

        )

    # ---------------------------------------------
    # Convert JSON -> Candle objects
    # ---------------------------------------------

        mapper = CandleMapper()

        return mapper.map_all(

            response["result"]

        )