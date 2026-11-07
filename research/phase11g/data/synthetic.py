"""Deterministic SYNTHETIC market-data fixtures (unit tests ONLY).

Every generator is seeded and labeled SYNTHETIC. Synthetic data must
never enter economic research results — tests assert the label.
"""

from __future__ import annotations

import random

SYNTHETIC = "SYNTHETIC"


def synthetic_trades(n=200, start=1787000000, price=100.0, seed=11):
    rng = random.Random(seed)
    out = []
    ts = start
    for i in range(n):
        ts += rng.choice([0, 0, 1])
        price += rng.choice([-0.5, -0.25, 0.0, 0.25, 0.5])
        out.append({"time": ts, "price": round(price, 2),
                    "quantity": round(rng.choice([0.1, 0.5, 1.0, 2.0]), 2),
                    "side": rng.choice(["buy", "sell"]),
                    "trade_id": "SYN-%d" % i,
                    "sequence": i,
                    "synthetic": True})
    return out


def synthetic_quotes(n=100, start=1787000000, mid=100.0, seed=12):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        spread = 0.5
        out.append({"time": start + i, "bid": round(mid - spread / 2, 2),
                    "ask": round(mid + spread / 2, 2),
                    "bid_size": 1.0 + (i % 5), "ask_size": 1.0 + ((i + 2) % 5),
                    "quote_id": "SYNQ-%d" % i, "sequence": i,
                    "synthetic": True})
    return out


def synthetic_book_updates(seed=13):
    return [
        {"kind": "snapshot", "time": 1000, "sequence": 1,
         "bids": [[99.5, 2.0], [99.0, 1.0]], "asks": [[100.5, 2.0], [101.0, 1.0]],
         "synthetic": True},
        {"kind": "delta", "time": 1001, "sequence": 2,
         "side": "bid", "price": 99.5, "quantity": 5.0, "synthetic": True},
        {"kind": "delta", "time": 1002, "sequence": 3,
         "side": "ask", "price": 100.5, "quantity": 0.0, "synthetic": True},
        {"kind": "delta", "time": 1003, "sequence": 4,
         "side": "ask", "price": 100.0, "quantity": 1.0, "synthetic": True},
    ]
