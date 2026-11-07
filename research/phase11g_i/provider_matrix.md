# 11G-I Provider Matrix (verified 2026-09; no invented endpoints)

| Provider | Market | Data | History | Resolution | Endpoint/Access | Auth | REAL/PROXY | Verdict |
|---|---|---|---|---|---|---|---|---|
| Delta Exchange | BTCUSDT/ETHUSDT perps | candles OHLCV | multi-year, windowed | 1m+ | GET /v2/history/candles (verified in-repo use) | none | REAL OHLCV | USE (existing) |
| Delta Exchange | perps | recent trades (50, maker/taker roles) | NO (count-capped recent) | tick | GET /v2/trades/{sym} (probed 11G-H) | none | REAL source, UNAVAILABLE historically | shape proof only |
| Delta Exchange | perps | L2 snapshot | NO (live only) | snapshot | GET /v2/l2orderbook/{sym} (probed 11G-H) | none | REAL source, UNAVAILABLE historically | shape proof only |
| Delta Exchange | perps | ticker OI/funding/mark | NO (snapshot) | snapshot | GET /v2/tickers/{sym} (probed 11G-H) | none | REAL source, UNAVAILABLE historically | shape proof only |
| Delta Exchange | perps | order/fills history | USER-OWN only | n/a | /v2/orders/history, /v2/fills (auth, own data) | key (not used) | N/A (not market data) | REJECTED (auth + not market-wide) |
| Binance Vision | BTCUSDT/ETHUSDT UM perps | aggTrades (isBuyerMaker aggressor) | daily+monthly since 2020, CHECKSUM per zip | tick (µs ms) | https://data.binance.vision/data/futures/um/daily|monthly/aggTrades/ (public) | none | REAL TRADES w/ aggressor | **ACQUIRE (this phase)** |
| Binance Vision | same | klines 1m | same depth | 1m | .../klines/ (public) | none | REAL OHLCV (cross-check) | acquire 1 day for validation |
| Binance Vision | same | mark/index/funding histories | documented | varies | futures markPrice/indexPriceKlines scripts (public) | none | REAL (deferred; not needed yet) | DEFERRED |
| OKX | spot/perp | trade history tick-level (claims Sep-2021+) | page-gated, login-ambiguous | tick | okx.com historical-data download pages | unclear | UNVERIFIED | REJECTED (access unclear, keep as fallback) |
| Bybit | spot/perp | trades + L2 | only via 3rd-party scraper or paid vendors | varies | no official bulk endpoint found | n/a | UNVERIFIED | REJECTED (no official bulk path) |
| Coinbase | spot | historic rates = candles only | yes | 1m | public REST | none | REAL OHLCV only | REJECTED (no tick; tick data paid) |
| Tardis/cryptostruct | multi | trades/book/quotes | yes, deep | tick | paid API/shop (free first-day-of-month CSV samples only) | key/paid | REAL but PAID | REJECTED (no paid commitments w/o authorization) |

Venue note: Binance UM BTCUSDT/ETHUSDT are different matching engines
from Delta's. Provenance records venue explicitly; cross-venue use in
future economics must account for basis/microstructure differences.
Feature mechanics (footprint math, delta, book) are venue-agnostic.
