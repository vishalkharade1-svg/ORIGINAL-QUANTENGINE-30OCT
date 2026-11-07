"""Read-only probe for Global Delta candlestick update/rollover behaviour."""

from __future__ import annotations

import argparse
import json
import time


def probe(endpoint: str, symbol: str, resolution: str, timeout: float) -> dict:
    from websockets.sync.client import connect

    channel = "candlestick_" + resolution
    updates: list[dict] = []
    with connect(endpoint, open_timeout=min(timeout, 15)) as socket:
        socket.send(json.dumps({"type": "subscribe", "payload": {"channels": [
            {"name": channel, "symbols": [symbol]},
        ]}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = json.loads(socket.recv(timeout=max(0.1, deadline - time.monotonic())))
            except TimeoutError:
                break
            if isinstance(raw, dict) and raw.get("type") == channel:
                updates.append(raw)
    starts = [frame.get("cst") for frame in updates if frame.get("cst") is not None]
    distinct = list(dict.fromkeys(starts))
    return {
        "channel": channel,
        "symbol": symbol,
        "updates": len(updates),
        "candle_start_values": distinct,
        "repeated_start_observed": len(starts) > len(set(starts)),
        "rollover_observed": len(distinct) > 1,
        "last_frame": updates[-1] if updates else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="wss://public-socket.delta.exchange")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--resolution", default="1m")
    parser.add_argument("--timeout", type=float, default=55.0)
    args = parser.parse_args(argv)
    print(json.dumps(probe(args.endpoint, args.symbol, args.resolution, args.timeout), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
