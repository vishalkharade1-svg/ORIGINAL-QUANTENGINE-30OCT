"""11G-I Binance UM aggTrades normalizer (REAL historical trades).

CSV columns: agg_trade_id,price,quantity,first_trade_id,last_trade_id,
transact_time,is_buyer_maker[,is_best_match].

Aggressor mapping (Binance-documented): is_buyer_maker=True means the
BUYER was maker → the SELLER aggressed → side=sell. False → side=buy.
Timestamps: transact_time is MICROSECONDS (16 digits); normalized to
integer MILLISECONDS (canonical event time).

Klines cross-check columns: open_time,open,high,low,close,volume,...
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g.events import canonical as EV  # noqa: E402


def parse_timestamp_us(raw):
    us = int(raw)
    if us > 10 ** 15:
        return us // 1000
    return int(us)


def side_from_buyer_maker(is_buyer_maker):
    s = str(is_buyer_maker).strip().lower()
    if s in ("true", "1", "t", "yes"):
        return "sell"
    if s in ("false", "0", "f", "no"):
        return "buy"
    raise ValueError("uninterpretable is_buyer_maker: %r" % is_buyer_maker)


def normalize_aggtrades_zip(zip_path, symbol, source):
    """Zip bytes path -> (TradeEvents chronological, stats)."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        text = z.read(names[0]).decode()
    reader = csv.DictReader(io.StringIO(text))
    events = []
    for row in reader:
        events.append(EV.TradeEvent(
            symbol=symbol,
            event_timestamp=parse_timestamp_us(row["transact_time"]),
            price=float(row["price"]),
            quantity=float(row["quantity"]),
            side=side_from_buyer_maker(row["is_buyer_maker"]),
            trade_id=str(row["agg_trade_id"]),
            source=source,
            provenance="REAL"))
    events.sort(key=lambda e: (e.event_timestamp, e.trade_id or ""))
    return events, {"rows": len(events), "member": names[0]}


def read_klines_zip(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        text = z.read(names[0]).decode()
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), names[0]


def cross_check_trades_vs_klines(trades, kline_rows):
    """Aggregate trades per minute; compare OHLCV against klines.

    Returns {minutes_compared, high_mismatches, low_mismatches,
    volume_diff_abs, volume_diff_rel}. Trade timestamps are ms;
    kline open_time is ms.
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for t in trades:
        buckets[t.event_timestamp // 60000].append(t)
    klines = {int(r["open_time"]) // 60000: r for r in kline_rows}
    compared = hi_bad = lo_bad = 0
    vol_diff = 0.0
    vol_base = 0.0
    for minute, ts in sorted(buckets.items()):
        if minute not in klines:
            continue
        k = klines[minute]
        px = [t.price for t in ts]
        if abs(max(px) - float(k["high"])) > 1e-9:
            hi_bad += 1
        if abs(min(px) - float(k["low"])) > 1e-9:
            lo_bad += 1
        v_tr = sum(t.quantity for t in ts)
        v_kl = float(k["volume"])
        vol_diff += abs(v_tr - v_kl)
        vol_base += v_kl
        compared += 1
    return {"minutes_compared": compared, "high_mismatches": hi_bad,
            "low_mismatches": lo_bad, "volume_diff_abs": vol_diff,
            "volume_diff_rel": (vol_diff / vol_base) if vol_base else None}
