# QuantEngine Phase 162 Market Data and Real-Time Transport Readiness

## Executive Summary
This document audits the market data ingestion, WebSocket transport, normalization, candle finality, and gap recovery systems within QuantEngine Phase 162.

---

## Adapter Inventory and Venue Isolation

### 1. Delta India Testnet Transport (Verified Active)
- **REST Base URL**: `https://cdn-ind-testnet.deltaex.org`
- **WebSocket URL**: `wss://cdn-ind-testnet.deltaex.org`
- **Authentication**: HMAC-SHA256 signature with sorted query params, method, timestamp, and payload. Dedicated environment variables: `DELTA_INDIA_TESTNET_API_KEY` and `DELTA_INDIA_TESTNET_API_SECRET`.
- **Status**: Verified active and empirically tested in Phase 162 (Candidates A and B). Zero leakage into generic production keys.

### 2. Delta Global Transport (Isolated Fail-Closed)
- **Status**: `BLOCKED_EVIDENCE`.
- **Boundary**: While public adapter logic exists in `core/exchanges/delta/`, live Global WebSocket streaming is not wired to production execution because authentic Global network rollover and venue-certified evidence are unavailable.
- **Fail-Closed Policy**: Runtime refuses connection attempts to Global endpoints without explicit operator authorization and verified credentials.

---

## Normalization and Ingestion Mechanics

### Symbol & Contract Mapping
- **Contract Loader**: `core/exchanges/delta/delta_contract_loader.py` dynamically queries active product specifications and builds canonical symbol representations.
- **Symbol Formatting**: Standardized symbol representation (e.g. `BTCUSD`, `ETHUSD`) with explicit underlying asset, quote currency, tick size, and lot size. Distinct contracts with similar names are prevented from aliasing.

### Timestamp Precision & Units
- **Contract**: All incoming exchange timestamps (whether in microseconds, seconds, or ISO strings) are normalized to integer Unix epoch milliseconds (`int(ms)`).
- **Enforcement**: Validated in `core/events/` and `core/bars/candle.py`. Out-of-order timestamps or negative intervals trigger immediate gap alerts.

### Event Ordering and Deduplication
- **Sequence Tracking**: Every incoming WebSocket channel frame (`l2_updates`, `v2/ticker`, `user_trades`) tracks monotonic sequence numbers.
- **Deduplication**: Replay cache drops duplicate sequence frames. Any detected sequence gap triggers automatic buffer hold and snapshot resynchronization.

---

## Candle Finality and Close Semantics

### Formation Protocol
- Candles are built from normalized raw trades and ticks via `core/bars/candle_event_emitter.py`.
- **Finality Flag**: A candle is marked `is_final=True` only when a trade occurs in a subsequent time bucket or explicit exchange close boundary is reached.
- **Anti-Lookahead Rule**: Downstream indicators, structure engines, and trade setup builders reject unfinalized (`is_final=False`) bars. Only completed bars are committed to the historical bar series.

---

## Gap Recovery and Resilience

### Stale-Feed Detection
- Monitored by `core/monitoring/service.py` and `core/runtime/realtime_engine.py`.
- If no message is received on an active subscription within the configured timeout threshold (default: 15 seconds), the feed is marked `STALE`, raising an alert and blocking new order intents.

### Historical Gap Recovery
- Integrated via `DeltaHistory.gap_candles()` in `core/runtime/verified_runtime.py`.
- **Exact-Range Recovery**: When a WebSocket disconnection is detected and restored, the gap recovery fetches only the exact missing 1-minute candle range.
- **Non-Synthetic**: Missing data is never synthetically interpolated or fabricated. If recovery fails, the system fails closed.

---

## Conclusion
The QuantEngine market data pipeline maintains strict transport isolation, precise normalization, deterministic candle finality, and robust fail-closed gap recovery.
