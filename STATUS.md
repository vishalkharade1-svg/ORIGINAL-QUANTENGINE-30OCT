# QuantEngine STATUS

> **NOTE -- 2026-08-28**: The original session log (items 1-73, ~579
> lines) was overwritten by a tooling error while appending the Session
> 7 entries below. It was not version-controlled and no backup copy
> exists on disk. Items 1-73 below are a BEST-EFFORT RE-CONSTRUCTION
> from the working-session record kept at the time; they summarize
> topics and outcomes but are NOT verbatim entries. If you keep your own
> copy (IDE local history, editor backup, or note), restore it over
> this file. Items 74-80 (Session 7) below are verbatim.

## Sessions 1-6 (reconstructed register)

### Session 1 - Bootstrapping / Stage 1-2
Worked against the existing QuantEngine build (no rebuild; one
problem at a time, upstream -> downstream). Confirmed repo layout,
engine registry, pipeline entry points, event bus. Candle builder
and history loading verified end-to-end on live Delta 1m candles.

### Session 2 - Stage 3/4 (Candles, MarketState, Context)
- Candle build from history: finished-bar semantics, warmup reverts
  guarded so short feeds never break downstream engines.
- PipelineContext fields/ownership; per-cycle reset protocol; the
  IndicatorEngine owns the shared IndicatorCache and is driven
  directly by InstitutionalPipeline.process() (not a registered
  engine) -- the historic double-registration failure mode.

### Session 3 - Stage 5/6 (Trengines, Indicators, Trend, Swing)
- Indicator ordering + warmup Nones contract; EMA/ATR/ADX/RSI series
  align with the bar window; latest() semantics.
- TrendEngine states (BULLISH/BEARISH/RANGE/WARMUP) and SwingEngine
  fractal scan, registry, institutional filter.

### Session 4 - Stage 7-9 (Structure, BOS, CHoCH, Liquidity)
- StructureEngine breaks; BOS/CHoCH mapping with strict dedupe;
  liquidity pool/target mapping and source_pool wiring; attachment
  conventions for swing/break/target objects.
- Contract test suites added for each stage; determinism proofs.

### Session 5 - Stage 10/11 (Displacement, FVG, Order Blocks)
- DisplacementScanner, FVGScanner, OrderBlockScanner publish sets
  into context (displacement / fvgs / order_blocks); ACTIVE vs
  NONE/archive lifecycle; live-data sweetening verified the scanners
  emit non-empty output; downstream no-lookahead score rules.

### Session 6 - Stage 12-15 (Setup, Decision, Risk, Execution,
Breaker/Mitigation wiring, .env drift)
- Setup+Decision: TradeSetupBuilder + DecisionEngine mapping, exact
  rejection reasons, FVG +3 bonus directionality, bounded quality;
  23-test contract suite (145 total).
- Risk+Execution: OrderIntent, RiskEngine (priority 750) sizes via
  PositionSizer into context.order/quantity, cost fields,
  TradeSimulator net PnL, Backtester account seeding + order-first
  execution; 14-test contract suite (159 total).
- Breaker/Mitigation: OrderBlockLifecycleEngine (325),
  BreakerEngine (330), MitigationEngine (331); FVGLifecycleEngine
  attempted then REMOVED (starved OB minting); live proof
  (5 breakers / 1 mitigation; regime TRANSITION 58 -> TRENDING 72);
  16-test contract suite (175 total).
- .env drift: RISK_PER_TRADE 1.0 -> 0.01 aligned to
  config/risk_settings.py (the value PositionSizer consumes); .env
  verified NOT git-tracked; temp .env.bak deleted.

## Session 7 (backtest speed -- approved indicator change + counter ids)

74. Profile drives the work. Live 1500-candle cProfile (identical data
    & harness, before): total 48.2s; IndicatorEngine.update 26.3s
    (EMA/ATR/ADX/RSI full-window recompute per candle), SwingEngine.scan
    15.5s, displacement 3.4s, uuid4+lambda ~4.5s, remaining engines ~2-3s.
    Per-candle indicator cost is O(window) by design: the sliding
    maxlen=1000 deque re-seeds EMA200/ATR/ADX/RSI from the truncated
    window start every candle, so cost scales O(candles x 1000).

75. Rejected attempt: SwingMetrics ATR-row memo (bit-identical, one
    file). Isolated A/B at full window showed 0.89x (SLOWER): ~66 swing
    confirmations/scans means a 1000-bar row build costs the same TR
    steps as the per-swing 14-bar loops it replaces. Reverted.

76. Implemented incremental indicators (EMA/ATR/ADX/RSI) -- APPROVED
    semantics change. update() is identical to calculate() for any
    non-continuation call (fresh engine, arbitrary/refed windows =>
    full recompute path), and appends one value per strict continuation
    pass (growth, or slide at the deque cap detected via
    bars[-2].timestamp == last seen). Full-history state carried in
    private fields; values trimmed to len(bars) so consumer alignment
    and latest() are untouched. calculate() rebuilds the state so
    mixed callers stay coherent. IndicatorEngine.reset() now clears
    each indicator (re-runs no longer continue stale state).
    Verified BIT-IDENTICAL to calculate() for all 400 prefixes across
    all six registered indicators; slide regime aligned and continuous
    at 1015 candles.

77. MarketObject.id switched from str(uuid4) to a monotonic counter
    ("MKT-N", opaque uniqueness; nothing parses the uuid format). All
    consumers use ids opaquely (registry dedupe, source_pool equality,
    parent/children refs). Output-identical.

78. Re-profile (same data, same harness, after): total 33.3s; indicators
    gone from the top-16 (was #1 at 26.3s); now dominated by
    SwingEngine.scan 22.4s, displacement 6.0s, uuid 0 (was ~6.7s).
    Measured speedup ~31% at 1500 candles. Full 5000-candle runs are
    noisy on this box (same build measured 153.9/165/199s), so the
    profiled totals are the reliable apples-to-apples signal.

79. Determinism + behavior diff (5000-candle live backtest, current
    build byte-stable across repeated runs): trades 28 -> 27. The ENTIRE
    change is ONE dropped trade -- a marginal +$15.07 win
    (BULLISH entry 80294.50 -> exit 80536.50, qty 0.0623). Final equity
    2997.81 -> 2982.74, explained 1:1 by that removed trade; the other
    27 trades are identical to the cent. Full suite 175/175 green,
    compileall clean.

80. Known remaining costs (all intrinsic O(window) reseans, identical
    behavior required): SwingEngine.scan rebuilds the full swing set
    every candle; displacement scanner re-scans its window. Both are
    the next candidates ONLY under an approved semantics change.

81. Reported bug: a trade setup scored 103. Root cause: TradeSetupBuilder
    seeds candidate.score = order_block.score (0..100) then adds an
    unconditional +3 FVG bonus with NO clamp (confidence was clamped,
    score was not) -- a perfect block + FVG => 103. TradeSetupScore and
    every other scorer already clamp to 0..100. Fix: min(candidate.score,
    100) applied at the same round() step (core/setup/trade_setup_builder.py).
    Behavioral proof: 5000-candle backtest byte-identical to the post-speed
    baseline after the fix (27 trades, PnL 982.7403408981611; elapsed 214.6s
    is the known machine-noise spread). Suite 175/175 green.

82. Backtest hardening. (a) backtesting/backtester.py::_book_closed_trades
    no longer books all()[-1] on ANY registry growth (which would silently
    under-book if a cycle ever closed two trades): it books the exact delta
    slice and RAISES RuntimeError if a cycle closes != 1 trade. New
    tests/test_backtester_hardening.py (7 tests, stdlib-only, fabricated
    candles, no pipeline) proves: ledger identity after a WIN/LOSS/WIN run
    (balance == starting + sum(closed pnl), realized == balance - starting,
    total == wins + losses == closed count); exactly-once booking with
    re-entry the cycle after a close + a bar-in-bar stop (execution
    precedes the bar's exit check, so same-cycle close+reopen is impossible
    by design -- an order is only actionable the cycle AFTER a close);
    same-bar stop exit books immediately; an order on the FINAL candle
    stays OPEN and is never force-closed at an imagined price (no
    lookahead); empty runs are no-ops; order-every-candle never breaches
    single-position (first-wins determinism); a double-close stub fails
    LOUDLY. Full suite 182/182 green (incl. the 7 new). 5000-candle
    backtest byte-identical after the change (27 trades, PnL
    982.7403408981611) -- behavior-neutral.

83. Cross-symbol validation (portfolio contract). New
    tests/test_portfolio_contract.py (11 tests, stdlib-only) proves the
    portfolio layer: (a) symbol ISOLATION -- two symbols each produce
    trades only from their own order script, with distinct engine/account/
    context objects and no bleed; the Backtester sets market.symbol from
    the CANDLE's declared symbol (candle-truth), so per-symbol candle
    tagging flows through to the per-symbol market state and ledger;
    (b) DETERMINISM -- two runs on the same PortfolioBacktester reproduce
    identical per-symbol trades; (c) AGGREGATION -- portfolio PnL equals
    the sum of per-symbol close PnL equals the sum over accounts of
    (balance - starting), and total booked trades equals the sum of the
    closed registries; (d) PortfolioRiskManager (risk/portfolio_risk.py,
    Build 7.4) -- max_portfolio_risk and max_positions caps reject
    overflow, close_trade releases exposure, counters never go negative,
    reset clears, and the bookkeeping invariant current_risk == sum of
    active risk / open_positions == active trade count holds; (e)
    legacy register(symbol, module) compat still auto-adds an engine.
    Full suite 193/193 green.

84. Dead-code quarantine (approved: keep-alive -> _archive/, no deletes).
    Import census proved the legacy tree is referenced ONLY by examples/
    scripts and intra-legacy imports -- nothing in core/data/config/
    backtesting/main.py/tests imports it -- and it DUPLICATES core/ classes
    under the master prompt's NO-duplicate-classes rule. Moved into
    _archive/ (off the import path, nothing lost): engine/, analysis/,
    smartmoney/ (16 files), strategy/, indicators/, signals/, execution/,
    analytics/, risk/risk_manager.py, plus the 22 examples/ scripts that
    demo only archived modules (test_bos, test_choch, test_confluence,
    test_decision_engine, test_displacement, test_execution, test_fibonacci,
    test_fvg, test_liquidity*, test_mtf, test_order_blocks*,
    test_position_manager, test_risk_manager, test_signal, test_strategy*,
    test_structure, test_trade_journal, test_warmup). 12 canonical examples
    remain in examples/. Kept live: backtesting/ (canonical backtester +
    portfolio), risk/portfolio_risk.py (now contract-tested). Proof:
    compileall clean; full suite 193/193 green; zero live imports of any
    archived package; risk.portfolio_risk still imports.

85. Delta universe expansion (request: backtester must trade ALL Delta
    products -- every crypto, options, tokens -- not just BTCUSD). Root
    gate was core/exchanges/delta/delta_contract_loader.py, which loaded
    perpetual_futures only; all 402 live products are now loadable and
    the full pipeline runs them. Changes: (a) core/exchanges/base_contract.py
    extended with optional metadata fields underlying_asset, option_type,
    strike_price, expiry_time (defaulted, non-breaking; nothing else
    constructs contracts besides the mapper); (b) core/exchanges/delta/
    delta_mapper.py hardened against REAL /v2/products payloads -- verified
    live that contract_type values are lowercase (call_options, put_options,
    binary_call_options, binary_put_options, perpetual_futures, spot),
    options/tokens carry None numeric fields (old float() mapping raised
    TypeError on first real option product), and underlying_asset is a DICT
    (asset object); mapper now coerces numerics safely (_num/_int, defaults),
    extracts the asset symbol, and derives option_type from contract_type
    (Delta emits no option_type/expiry_time field; direction lives in
    contract_type + C-/P- symbol prefix, expiry in the symbol tail);
    (c) delta_contract_loader.load() now accepts contract_types=None and
    loads EVERYTHING by default, with a whitelist param restoring the
    old perpetual-only behavior; (d) config/settings.py gains UNIVERSE
    (env UNIVERSE, default "explicit"; "all" = full universe via
    loader .all()); (e) examples/test_portfolio_backtester.py honors
    UNIVERSE=all; (f) tests/test_delta_loader.py (5 tests, DeltaProducts
    stubbed, no network) pins the full-universe contract behind the real
    schema. Proof: live probe loads 402 products by type
    {put_options: 185, call_options: 187, perpetual_futures: 12,
    binary_put_options: 6, binary_call_options: 6, spot: 6}; option
    option_type/strike/underlying metadata verified on real payloads;
    full suite 198/198 green (193 + 5 loader); compileall clean. End-to-end
    instrumented run over 5k bars/symbol on BTCUSDT (perp), P-BTC-61000
    (put option), SOL_USDT (tokenized spot): pipeline fully healthy on ALL
    three (100,000 engine calls, 0 errors, per-symbol isolation); trades
    fired ONLY on BTCUSDT (309 accepted decisions -> 11 trades) while the
    option/spot series formed no qualifying setups in-window -- a strategy
    setup-formation outcome, NOT a loader/pipeline blocker. Honest caveats:
    (1) option strikes only film candles where traded volume exists --
    untraded strikes and far-dated expiries return no data, so setups can
    exist only on liquid strikes; (2) full universe is 402 products, each
    x history pages -- run bounded via SYMBOLS or UNIVERSE=all as load
    budget allows.


86. Bounded multi-symbol live portfolio run (request follow-through:
    prove the backtester trades beyond BTCUSDT). Ran the FULL Delta
    universe pick through PortfolioBacktester with live candles:
    14 symbols = all 12 perpetual_futures (BTCUSDT, METAXUSDT, XRPUSDT,
    GOOGLXUSDT, TSLAXUSDT, AAPLXUSDT, NVDAXUSDT, ETHUSDT, DOGEUSDT,
    AMZNXUSDT, PAXGUSDT, SOLUSDT) + P-BTC-61000-280826 (put_options) +
    SOL_USDT (tokenized spot), 2000 1m candles each, identical pipeline
    (20 engines, per-symbol isolation). Result: 12 trades / +690.64 PnL
    across THREE distinct symbols -- BTCUSDT 9 trades +246.98, ETHUSDT
    2 trades +273.52, SOLUSDT 1 trade +170.14; the other 9 perps, the
    put option and the spot ran their full 2000 bars cleanly (trades 0
    -- setups simply did not qualify in-window, consistent with item 85
    findings). Confirms the universe gate is fully lifted: the portfolio
    layer now trades every Delta listed instrument, perps the most
    naturally on this strategy. No semantics changed; live-data outcome
    (not deterministic byte-stable -- network-sourced candles vary).


87. Incremental swing ATR (APPROVED semantics change -- the STATUS 80
    named remaining cost). Profile first (1500-candle canonical harness,
    single-subscription -- my initial profile double-subscribed on_candle
    into a full-duplicate candle every pass, which breaks the indicator
    continuation check bars[-1].timestamp != _last_ts and made indicators
    re-appear at 70s; the canonical path subscribes once, so that was a
    harness artifact, not a regression). Correct profile: 24.0s total,
    SwingEngine.scan 14.9s (62%), of which swing_metrics.calculate 6.9s.
    Root: scan() rebuilds the full swing set every candle and recomputes
    each swing's atr() as a fresh 14-terms-per-swing loop (93,460 metric
    calls). Fix, all in core/market_structure/swing_metrics.py (+wiring in
    swing_engine.reset()): memoize each physical bar's true-range ONCE by
    timestamp (_tr_cache) and, on top, memoize each physical ATR window
    (_atr_cache) so atr() is a single dict get per swing instead of 14
    lookups+13 adds. Bit-identical: cached TRs are summed in ascending
    position order, exactly the classic loop. Contract proof: new
    tests/test_swing_metrics_incremental.py (4 tests, stdlib-only,
    fabricated bars) asserts atr() == a reference per-call loop across a
    full window AND across an incremental growing/sliding feed at EVERY
    index (cap 100), calculate() == reference metrics, reset() clears the
    memo and re-runs identical. Behavior proof: 5000-candle live snapshot
    BYTE-IDENTICAL before/after (account block + all 34 trades identical,
    balance 3074.075887, realized 1074.0758865299547). Re-profile: 24.0s
    -> 18.4s (TR memo) -> 15.4s (+ATR memo), 2.9x cut on swing_metrics
    (6.9s -> ~2.4s region), total ~36% faster; function calls 11.2M ->
    7.6M. Remaining known costs unchanged: displacement scanner 3.5s,
    the scan() fractal loop itself 4.1s tottime -- same class of
    incremental work as item 80's other named candidate. Full suite
    202/202 green (198 + 4 new), compileall clean.


88. Fuller universe re-run (evidence snapshot, 5000 bars/symbol). Same
    14-symbol set as STATUS 86 (12 perpetual_futures + P-BTC-61000 put
    option + SOL_USDT tokenized spot) but 5000 1m candles each, taking
    advantage of the STATUS 87 speedup. Outcome: 47 trades / +4164.75
    closed PnL across FOUR distinct symbols -- BTCUSDT 26 trades
    +1993.99, ETHUSDT 20 trades +1819.88, SOLUSDT 1 trade +350.87,
    PAXGUSDT 0 / others 0. Deeper history surfaced trades on more
    instruments than the 2000-bar STATUS 86 window (which had fired on
    3 symbols / 12 trades), and the two majors dominate PnL as expected.
    Role played per-symbol on full 5000 bars, pipeline healthy
    everywhere. Two honest notes: (a) P-BTC-61000-280826 returned an
    empty history DURING the crawl despite later probes confirming a
    full 5000-candle series -- a transient fetch artifact, not a loader
    fault; a targeted re-run of exactly that option through the portfolio
    pipeline confirms full bars, 100,000 engine calls, 0 errors, 0 trades
    (same valid-no-qualifying-setup outcome as STATUS 85/86); (b) spot
    (SOL_USDT) and thin perps (DOGEUSDT, METAXUSDT, XRPUSDT, GOOGLXUSDT,
    TSLAXUSDT, AAPLXUSDT, NVDAXUSDT, AMZNXUSDT, PAXGUSDT) ran clean but
    produced no qualifying setups in-window -- on this strategy perps
    with strong 1m displacement remain the natural fit. No code changed;
    suite remains 202/202.


89. Housekeeping pass (docs + hygiene; docs-only change). Selected by the
    user over the displacement+fractal speedup thread (item 80's
    remaining candidate). (a) Import census + grep confirmed ZERO live
    imports of archived packages and no archived paths in the 12
    canonical examples. (b) Reconciled docs/import_manifest.md with the
    live tree: added the previously-missing EXCHANGES section
    (core/exchanges/*, 11 delta modules) with verified imports; replaced
    stale bare-name entries (indicator_engine.py, TrendEngine,
    DisplacementScanner, etc.) with real module paths; corrected the
    SIMULATION section to live modules (trade_simulator, risk_engine,
    account) and removed the quarantined PositionManager/Portfolio
    entries; folded OPTIMIZATION/AI/LIVE into a single QUARANTINED note
    (OptimizationEngine/AIEngine/BrokerEngine are NOT importable); fixed
    event/pipeline/data imports to match AST-verified actuals; removed
    the nonexistent config/secrets.py entry (no live importer); header
    Last Updated updated. Validated with a script that parses every
    documented module's imports vs. AST-discovered imports -- 47/47
    modules match, 0 issues. (c) Git hygiene finding (NO ACTION TAKEN,
    reported only): .env and .venv/ appear as STAGED deletions (removed
    from tracking, awaiting commit) and logs/engine.log is still a
    tracked file -- recommend untracking logs/ before any future commit.
    Docs-only change; full suite 202/202, compileall clean.


90. Incremental scan speedup (APPROVED semantics change, item 80's named
    candidate). The two remaining O(window) rescans are now incremental,
    with byte-identical output. (a) core/market_structure/swing_engine.py:
    SwingEngine.scan previously re-derived the left/right fractal flags
    for every in-window bar at every relative slot each candle -- the
    window is fixed for a bar once it is scannable, so the flags are
    cached per absolute bar index in _fractal_cache, gated on bar
    identity (a fresh session or different symbol recomputes instead of
    reusing stale flags); reset() clears it. (b) core/displacement/
    displacement_scanner.py: volume_ratio and liquidity_sweep are the
    only fields reading a lookback window; both are cached per absolute
    index in _window_cache with the exact original gate -- when a bar
    slides to relative position < LOOKBACK (lookback window partially
    dropped from the trailing deque) the fields report 0/False, matching
    the original rescan. Verification: (1) byte-identical snapshot on a
    ONE fixed 5000-candle feed A/B'd before vs after (33 trades, all
    fields equal; only elapsed differs, 165.2s -> 118.1s, ~1.4x on
    identical data); (2) live snapshot harness also byte-identical
    (earlier 2983.26 vs 3009.67 gap was live-data drift between fetches,
    proven by the fixed-data A/B); (3) 1500-candle profile: scan tottime
    5.08s -> 2.51s, the ~650k min() + ~307k max() window calls gone;
    (4) new tests/test_incremental_scan.py -- 4 tests locking in
    memo==full-rescan determinism and reset-clears-state for BOTH
    engines, incl. the reference recompute of window fields. Suite
    206/206 (202 + 4 new), compileall clean. Manifest unaffected
    (imports unchanged in both files).

91. Delta Order Executor (roadmap: Delta Order Executor; unblocks Paper
    + Live). Selected by the user as the next build after the STATUS 90
    speed-up thread. Delta v2 private endpoints require an HMAC-SHA256
    signature over method + timestamp + path-with-query + body, hex-
    encoded, with the same seconds timestamp in the header (verified
    against docs.delta.exchange). (a) NEW core/exchanges/delta/
    delta_auth.py: build_prehash/sign/query_string primitives + a
    DeltaSignedREST client (get/post/delete) that serializes a POST body
    ONCE and signs and sends that exact string; public endpoints stay
    callable unsigned. (b) core/exchanges/delta/delta_exchange.py: the
    historical NotImplementedError stub is now a REAL adapter --
    place_order (POST /v2/orders), cancel_order (DELETE /v2/orders/{id}),
    get_order (GET /v2/orders/{id}), get_balance (GET /v2/wallet/
    balances), get_positions (GET /v2/positions), get_products (public),
    get_product_id(symbol) product-id lookup, and a _require_auth guard
    that refuses private endpoints without DELTA_API_KEY/SECRET (config/
    settings.py already read them). State confirm: get_order was declared
    but previously never implemented. (c) NEW core/execution/order_
    executor.py -- DeltaOrderExecutor maps the SAME OrderIntent RiskEngine
    produces into context.order (Signal -> Risk -> Order Intent ->
    Execution Adapter): side from direction (BULLISH->buy, BEARISH->
    sell), product_id + price/quantity precision from the contract
    registry (DeltaContractLoader->DeltaMapper), GTC limit at entry, and
    native Delta bracket TP/SL attached when the intent carries both;
    invalid intents are rejected without touching the exchange, missing
    contracts raise. (d) core/exchanges/base_contract.py gains the
    optional metadata field product_id (default 0; non-breaking, matches
    the STATUS 85 optional-metadata pattern) and core/exchanges/delta/
    delta_mapper.py extracts it from the real /v2/products `id` field.
    (e) NEW canonical example examples/test_delta_order_executor.py
    (dry-run by default; DELTA_EXECUTE=1 places for real). Proof:
    compileall clean; full suite 252/252 green (220 + 32 new: 13 delta_auth
    signature-contract tests locking the documented pre-hash format
    against an independently-computed hmac, 8 delta_exchange endpoint
    tests, 11 order_executor tests, in test_delta_auth.py /
    test_delta_exchange.py / test_order_executor.py; test_delta_loader
    unchanged); example verified headless. No pipeline semantics changed.
    Docs: import_manifest.md registered delta_auth.py + order_executor.py
    and refreshed delta_exchange imports; project_manifest/PIPELINE_*
    unchanged (no new context variables, no engine order change).


92. Paper Trading Engine (roadmap: Paper Trading -- the step immediately after the STATUS 91 Delta Order Executor, selected by the user). NEW core/paper_trading/paper_trading_engine.py -- a feed-driven PaperTradingEngine that reuses the canonical institutional pipeline end-to-end with NO exchange credentials, sharing the EXACT Backtester execution flow: the engine resets the per-candle cycle, publishes market state, publishes the paper account's live AccountState into context (so RiskEngine sizes next orders from current paper equity), then drives pipeline.on_candle EXPLICITLY (not via EventBus dispatch) so the institutional flow + RiskEngine OrderIntent ALWAYS complete before the fill -- subscription order on the bus can never starve the engine. Per-candle it then fills the OrderIntent via the SAME shared TradeSimulator with the intent's quantity/commission/slippage, runs TradeSimulator.update for SL/TP management, books closed P&L into the SAME Account (with the loud exactly-one-close guard), and optionally marks the open trade to market. Two opt-in knobs default to backtest-identical behavior: fill_slippage_bps (0.0 = fill exactly at intent entry; >0 = buys fill entry+bps, sells entry-bps, stops/targets unchanged -- modeled via a non-mutating attribute adapter so any OrderIntent or plain setup works) and mark_to_market (False = equity only moves on booked closes like the Backtester; True = floats net unrealized P&L, less modeled commission+slippage, into equity each candle). main.py now wires PAPER_MODE (config/settings.py default True): the PaperTradingEngine subscribes to the live CandleEvent feed and drives the pipeline; without paper mode the pipeline subscribes directly (live analyze-only). NEW canonical example examples/test_paper_trading.py mirrors the portfolio example's wiring (HistoricalLoader + CandleBuilder + InstitutionalPipeline) and replays 500 BTCUSDT bars headlessly. Proof: compileall clean; full suite 272/272 green (252 + 20 new test_paper_trading contract tests: fill semantics, ledger identity win/loss/win, same-bar stop, re-entry, single-position first-wins, pipeline-driven-before-fill, live account state published into context, reset cleanliness, fill_slippage_bps buy/sell, mark_to_market float/net-of-costs/track/reset, subscribe registers the CandleEvent callback). Example verified end-to-end against live Delta history. Docs: import_manifest.md gained the PAPER TRADING section (STATUS 92) + header refresh; PIPELINE_CONTEXT_OWNERSHIP/project_manifest already listed PaperTrading as a reader of execution_signal/order -- no ownership change (no new context variables, no engine-registry order change).


93. BrokerEngine / Live Trading (roadmap: LIVE TRADING -- the manifest's remaining live item after Paper Trading, selected by the user). NEW core/live/broker_engine.py -- BrokerEngine, the LIVE consumer that routes the SAME RiskEngine OrderIntent the Backtester and PaperTradingEngine consume to the REAL Delta exchange through the STATUS 91 DeltaOrderExecutor, tracks the open position from exchange positions, and books closed P&L into the SHARED TradeRegistry + Account (no new classes; the registry + Trade + Account + TradeSimulator are all reused). Drives the same pipeline-first flow as Paper/Backtest: reset cycle, market/account publish into context (RiskEngine sizes from synced equity), explicit pipeline.on_candle, then route when flat, then manage/close. DRY-RUN IS THE DEFAULT: dry_run=True records each would-be intent on the placed audit trail and manages a paper position through the same TradeSimulator (zero exchange writes, fully offline/testable); live placement is an explicit opt-in (settings.LIVE_EXECUTE=1 and DELTA_API_KEY/SECRET; the STATUS 91 DeltaExchange._require_auth guard is a second backstop). Live mode is exchange-authority: zero-size position records are NOT positions (the open-order fill watch clears a cancelled/expired/rejected order so a dead order never blocks reuse); a close books ONE Trade with the exchange-reported exit price / realized P&L (already net of fees -- modeled costs are dropped to avoid double counting; when the exchange reports no exit/pnl the engine nets the intent's modeled commission+slippage like the simulator); account equity is re-synced from executor.balance() when flat. Live position/trade responses are read via tolerant candidate field names (_field / _fields_list) so Delta's JSON schema can drift without breaking the engine. Wiring: config/settings.py gains LIVE_MODE + LIVE_EXECUTE; main.py now selects PAPER (default) / LIVE (BrokerEngine + DeltaOrderExecutor, dry unless LIVE_EXECUTE=1) / ANALYZE-ONLY. NEW canonical example examples/test_live_broker.py mirrors the paper example (HistoricalLoader + InstitutionalPipeline) and is dry-run by default. Proof: compileall clean; full suite 287/287 green (272 + 15 new test_broker_engine contract tests: 7 dry-run including ledger identity via backtest-style candle exits, single-position first-wins, pipeline-driven-before-route, live account state published into context, reset, subscribe; 8 live via a recording fake executor: places-and-captures-order-id, close books once with exchange P&L, no same-candle double re-entry, re-entry on next candle, rejected order opens nothing, open-order watch clears cancelled, equity synced from exchange). Example verified end-to-end headless (auto-driven; no intents on the demo 500-bar window -- same as the paper example). Docs: project_manifest.md marked PaperTradingEngine and BrokerEngine Active (STATUS 92/93); import_manifest.md added the LIVE TRADING section (STATUS 93) registering broker_engine imports, corrected the quarantined-note claim that there was no live broker stage (the archived legacy broker is distinct from the new core.live BrokerEngine), refreshed the header + LIVE import surface; OBJECT_OWNERSHIP readers now list Live Trading (BrokerEngine); PIPELINE_CONTEXT_OWNERSHIP already named BrokerEngine a reader.


94. Performance Analytics (roadmap: PERFORMANCE ANALYTICS -- the analytics layer documented as the reader of backtest_result / portfolio, selected by the user after STATUS 93). NEW core/analytics/performance.py -- PerformanceAnalytics + PerformanceReport that consume the SHARED TradeRegistry + Account state every execution mode (Backtest, Paper, Live Broker) books into: the exact objects those engines wrote, so no reconciliation is needed and the NO-duplicate-classes rule holds (nothing is duplicated). analyze(account, trades) accepts an Account or AccountState and a TradeRegistry or any sequence of Trade objects; open trades are excluded so the report is stable per book. Metrics: total/wins/losses, win rate, gross profit/loss, profit factor (+inf when only wins), expectancy, avg win/loss, payoff ratio, avg PnL %, avg bars held, best/worst trade, exit-order win/loss streaks, longs/shorts counts and win rates, and trade-based Sharpe / Sortino (sample-std of the per-trade PnL series scaled by sqrt(N), downside deviation for Sortino). Equity curve = closed trades sorted by exit_time applied to the starting balance, with peak equity and the peak-equity drawdown (amount + percent) measured on the curve -- independent of, and reconcilable with, the AccountState drawdown. Also exposes metrics() (JSON-friendly dict) and summary() (console block). NEW tests/test_performance_analytics.py -- 12 stdlib-only contract tests locking exact metric values on deterministic win/loss mixes, exit-order equity curve, curve drawdown, streaks, directional breakdown, Sharpe on a small series, only-wins -> +inf profit factor, open-trade exclusion, reconciliation with a booked Account (net_profit == realized_pnl, final_equity == balance), and the dict/console forms. NEW canonical example examples/test_performance_analytics.py runs the STATUS 92 paper replay then feeds paper.account + paper.trades into PerformanceAnalytics.summary + the equity curve; verified headless (zeroed report on the demo 500-bar window, same as the other examples). Proof: compileall clean; full suite 299/299 green (287 + 12 new). Docs: import_manifest.md added the PERFORMANCE ANALYTICS section (STATUS 94, imports AST-verified: core.backtesting.trade_registry + stdlib dataclasses) + header refresh; project_manifest.md registered PerformanceAnalytics Active; PIPELINE_CONTEXT_OWNERSHIP / OBJECT_OWNERSHIP already name Analytics as the reader of backtest_result/portfolio/trade_simulator -- no ownership change (no new context variables, no pipeline/engine order change).


95. Portfolio Manager (roadmap: PORTFOLIO MANAGER -- the last item left in the documented Portfolio Manager -> Order Executor -> Performance Analytics architecture chain; user-selected after STATUS 94). EXTENDED the SHARED PortfolioRiskManager (risk/portfolio_risk.py) IN PLACE under the NO-duplicate-classes rule instead of creating a competing PortfolioEngine: the legacy dollar-risk pool (max_portfolio_risk) + position count (max_positions) semantics are byte-identical when the new guards default off, then added three layers of portfolio control, all opt-in: daily_loss_limit ($ floor on equity; once realized PnL lags starting_balance by the limit every order is gated, wins restore equity and re-enable), max_portfolio_allocation / max_per_symbol_allocation (open notional locked against OrderIntent.position_value, % of current equity, tracked per symbol so a close releases exactly its own exposure). PortfolioBacktester (backtesting/portfolio_backtester.py) now passes order.symbol + order.position_value through _portfolio_gate and Trade.symbol + Trade.pnl through _portfolio_release. Supporting enrichment: core/backtesting/trade.py carries a new symbol field (default '' -- slots-dataclass backward compatible) populated by TradeSimulator.open_trade from OrderIntent.symbol (getattr-safe for all open_trade callers: Backtester, ReplayPath, PaperTradingEngine, BrokerEngine). NEW tests/test_portfolio_manager.py -- 11 stdlib-only tests: legacy cap neutrality with guards disabled, daily-loss gate + recovery, portfolio allocation cap, per-symbol cap independence, notional release on close, zero-equity guard, equity == starting + realized, reset clears current_risk/open_positions/open_by_symbol/realized_pnl, plus three PortfolioBacktester integration runs proving the floor blocks later symbols end-to-end and the allocation cap blocks/ releases a second symbol's order. Example examples/test_portfolio_risk.py rewritten into the canonical Portfolio Manager demo (BTC/ETH/SOL/ADA scripted orders: allocation caps block ADA at the 60% portfolio ceiling; BTC closes release notional + realized PnL). Proof: compileall clean; full suite 310/310 green (299 + 11 new, zero existing-test changes needed); Trade.symbol enrichment verified non-breaking across backtester/paper/broker suites. Docs: import_manifest.md added the PORTFOLIO MANAGER section (STATUS 95, portal wiring documented; header refresh); project_manifest.md dropped stale Draft entries -- Portfolio -> Active PortfolioRiskManager, portfolio_backtester.py -> Active multi-symbol driver; no new pipeline/context variables so PIPELINE_CONTEXT_OWNERSHIP unchanged.


96. Performance Dashboard (roadmap: PERFORMANCE DASHBOARD -- user-selected after STATUS 95; the display layer that completes the Performance Analytics line). NEW core/dashboard/dashboard.py + __init__.py -- PerformanceDashboard, a PURE display layer over the SHARED PerformanceReport the analytics layer (core/analytics, STATUS 94) produces. Reads ONLY that report + the closed trade sequence; nothing is recomputed and no new state object is created (No-duplicate-classes / No-duplicate-state hold), so the console block, ASCII equity curve, trades table and CSV export can never disagree with the metrics any mode prints. Four methods: (a) render(report, label) -- aligned stat block that ADDS the report rows the analytics summary omits (peak equity, gross profit/loss, avg PnL %, avg bars held, returns std, W/L streaks); (b) render_equity_curve(report, height, width) -- ASCII log-line chart of the trade-based equity curve with peak/trough scale labels and an exit-time timeline, WATERFILL bars, 'No closed trades to chart.' notice on an empty report; (c) render_trades(report, trades, limit) -- recent-trades table over the analytics closed-only view (open trades never listed); (d) export_csv(trades, path=None) -- deterministic exit-ordered CSV (symbol, direction, entry, exit, entry_time, exit_time, bars_held, pnl, pnl_percent, commission, slippage, result), returns the CSV text or writes the file and returns the path. NEW tests/test_performance_dashboard.py -- 9 stdlib-only tests: render contains the report rows incl. the analytics-summary-omitted ones + zeroed report; chart full-height on a monotonic climb + valley reaching the trough label + no-trades notice; open trades never rendered; CSV header/round-trip determinism (exit order 1,4,7), symbol column, real file write via tempfile, Registry+open-trade exclusion. NEW canonical example examples/test_performance_dashboard.py runs the STATUS 92 paper replay then renders stat block + equity curve + trades table + CSV preview (temp file cleaned up); verified headless (zeroed report on the demo 500-bar window, same as the other examples). Proof: compileall clean; full suite 319/319 green (310 + 9 new). Docs: import_manifest.md added the PERFORMANCE DASHBOARD section (STATUS 96; AST-verified imports core.analytics.performance + core.backtesting.trade_registry) + header refresh; project_manifest.md registered PerformanceDashboard Active; no new pipeline/context variables, so PIPELINE_CONTEXT_OWNERSHIP / OBJECT_OWNERSHIP unchanged.


97. Validation Layer -- Walk-Forward Testing + Monte Carlo + Strategy Optimizer (roadmap: WALK FORWARD TESTING / MONTE CARLO / STRATEGY OPTIMIZER -- the validation trio; user-selected after STATUS 96). NEW core/validation/ package consuming ONLY the canonical Backtester flow and the SHARED PerformanceAnalytics report + trade objects (No-duplicate-classes/state hold -- no engine is rewritten, every run calls the caller's runner(bars, config) -> (account, trades) over the real pipeline). (a) walk_forward.py -- WalkForwardTester carves the history into sequential folds (train window immediately followed by a never-seen test window, advancing by step); optional candidates picked per fold on the train window by an in-sample metric (net_profit / sharpe from the shared report), then that config runs the test window out-of-sample; WalkForwardFold carries train/test ranges, best_config, in_sample + out_of_sample reports, oos pnl/trades/sharpe; WalkForwardResult sums oos trades + net profit; no engine state crosses folds. (b) monte_carlo.py -- MonteCarloSimulator bootstraps (WITH replacement) the closed-trade PnL sequence of any mode (TradeRegistry or sequence; open excluded, matching analytics), re-walks the equity curve from the starting balance per sim, Random(seed+index) makes it fully deterministic; MonteCarloResult: mean/P25/P50/P95/worst net profit, mean + P95 max drawdown (and % of balance), survival rate (never hit equity <= 0), raw samples, console summary(). (c) optimizer.py -- StrategyOptimizer cartesian grid sweep (itertools.product, max_combos guard) over a param grid; runner(bars, params) per combo; ranked descending by a configurable metric (net_profit / sharpe / profit_factor / win_rate) read off PerformanceAnalytics.metrics; OptimizationRun exposes props + full metrics dict; .best = top row. NEW tests: 18 stdlib-only total -- test_walk_forward.py (5: fold carving, candidate selection + OOS, plain windows, overlapping step, guards), test_monte_carlo.py (8: constant-sequence exactness, seed reproducibility + different-seed divergence, mixed-sequence distribution + percentile ordering + survival bounds, empty valid, closed-only view, Registry input, bad-simulations guard, summary render), test_optimizer.py (5: winning-param ranking + total trade counts, cartesian ranking by win_rate with a discriminating win/loss candle series, complete metrics dict, best-none-before-run, guards). NEW canonical example examples/test_validation.py runs the full institutional pipeline replay over real BTCUSDT history and drives all three on the IDENTICAL flow with risk_settings.RISK_PER_TRADE as an honest strategy knob (optimizer genuinely resizes reporter orders: folder demonstrated headless on the zero-trade demo window like the other examples; unit tests prove nonzero discrimination on synthetic parametric pipelines). Proof: compileall clean; full suite 337/337 green (319 + 18 new, zero existing-test changes). Docs: import_manifest.md added the VALIDATION LAYER section (STATUS 97; AST-verified imports: walk_forward+optimizer -> core.analytics.performance, monte_carlo -> core.backtesting.trade_registry, __init__ none) + header refresh; project_manifest.md registered the three tools Active; no new pipeline/context variables so PIPELINE_CONTEXT_OWNERSHIP unchanged.


98. Position Manager (roadmap: POSITION MANAGER -- the remaining Draft in project_manifest; user-selected after STATUS 97). NEW core/risk/position_manager.py -- PositionManager, execution-layer hygiene that is deliberately the INVERSE of the legacy archived execution/position_manager.py (which owned its own Position object + SL/TP state and was quarantined under the No-duplicate-classes rule): the live manager keeps NO state of its own, reads every position from exactly where the architecture puts it (TradeSimulator.current_trade / TradeRegistry), and relies on TradeSimulator.update for SL/TP. Two stateless responsibilities: (a) ORDER REFINEMENT applied at the SINGLE choke point TradeSimulator.open_trade, so Backtest / Paper / Live Broker all book the same corrected quantity: round to QUANTITY_PRECISION decimals, cap notional (entry*quantity) at MAX_ALLOCATION_PER_TRADE and optionally LEVERAGE*equity (manage_into), and drop dust -- any quantity below MIN_QUANTITY invalidates (quantity -> 0, no trade opens). manage()/audit() are PURE and idempotent: OrderIntents via dataclasses.replace, non-dataclass order shapes (the paper _SlippageAdjustedOrder wrapper) via the pure _ManagedOrder attribute-adapter, the SetupCandidate signal fallback (no quantity/entry) passes through unchanged so the legacy fallback path stays byte-identical; audit() returns (corrected, reasons) for observability. TradeSimulator default-constructs the manager, so enforcement is ON with zero wiring changes (all pre-existing flows unaffected -- full suite needed zero test edits bar none). (b) POSITION READING: unrealized(trade, price) and snapshot(trade, price) compute entry-value, unrealized PnL + %, and WIN/LOSS/FLAT from the shared open Trade. config/risk_settings.py adds QUANTITY_PRECISION = 8 and MIN_QUANTITY = 1e-6 (MAX_ALLOCATION_PER_TRADE / LEVERAGE pre-existed and are now enforced at the choke point too). NEW tests/test_position_manager.py -- 14 stdlib-only tests: rounding, notional cap scaling (10 @ 1000 -> 0.5), leverage*equity cap, dust invalidation + reasons, purity (input untouched) + idempotence, clean-order no-op, plain-order refinement through the proxy with faithful passthrough + untouched original, SetupCandidate passthrough, bull+bear unrealized exact values, snapshot keys/state, and THREE canonical integrations: Backtester books the capped quantity, dust order opens nothing, and the PaperTradingEngine slippage-wrapper path still refines (quantity capped to MAX_ALLOC/100.1 at the slipped fill entry, original intent untouched). NEW canonical example examples/test_position_manager.py audits a sample 10-lot @ 1000 order (capped to 0.5, reasons listed, original intact) then runs the STATUS 92 paper replay and prints live snapshots of the open position -- verified headless: the pipeline's own RiskEngine-sized order lands at EXACTLY 500.00 notional, proving the MAX_ALLOCATION enforcement live at the choke point. Proof: compileall clean; full suite 351/351 green (337 + 14 new, zero existing-test changes). Docs: import_manifest.md added the POSITION MANAGER section (STATUS 98; AST-verified imports config.risk_settings + core.risk.order_intent, plus TradeSimulator's new core.risk.position_manager edge) + header refresh; project_manifest.md flipped the stale PositionManager AND TradeSimulator Draft entries to Active; config additions documented; no new pipeline/context variables so PIPELINE_CONTEXT_OWNERSHIP unchanged.

99. Execution Lifecycle (Phase 4C -- user-selected after STATUS 98; the fix for the duplicate "EXECUTION SIGNAL" replay logs and over-ordering/duplicate-fill defect). Enforced invariant: ONE SETUP ID == MAXIMUM ONE PRIMARY ORDER == MAXIMUM ONE PRIMARY TRADE, identical across Backtest / Paper / Live Broker. ROOT CAUSE, two layers: (1) InstitutionalPipeline.__init__ already registers one ExecutionEngine; the scripting layer (tests/test_backtester.py and 7 examples) appended a SECOND via register(), which deduped by object identity, NOT name, so the pipeline ran [DecisionEngine, ExecutionEngine, ExecutionEngine, RiskEngine] and every accepted setup was emit-processed twice; (2) a SetupCandidate had NO identity -- the same order block + prices re-derived as a fresh object every bar and were re-ordered bar after bar, and the backtester filled whatever context.execution_signal said with no consume-once or entry-touch check. FIX: NEW core/execution/order_registry.py -- the persistent, cross-cycle, cross-mode source of truth living on the shared PipelineContext (created in __post_init__, re-created on reset(), deliberately NOT cleared by reset_cycle()). Lifecycle NEW -> PENDING -> FILLED|CANCELLED|REJECTED|EXPIRED; create() mints [setup_id]-ORDER-N and is duplicate-proof (one primary order per setup_id); advance() ages pending orders and EXPIRES any beyond MAX_WAIT_BARS; mark_filled() consumes a PENDING order exactly once and mints [order_id]-TRADE-N onto both order and Trade. Setup identity: trade_setup_builder.py stamps setup_id "[symbol]-[timeframe]-[direction]-OB-[index]-[entry]-[stop]-[target]" from the stable OrderBlock index; setup_candidate.py carries setup_id + lifecycle (NEW->ACCEPTED->ORDER_CREATED->FILLED/EXPIRED via the registry); decision_engine.py logs SETUP_ACCEPTED at most once per setup_id per run. execution_engine.py is now idempotent (clears the signal the instant its selected setup already has a registry order -- the earliest guard); risk_engine.py is the canonical emit point and re-checks has_order_for_setup, stamps setup_id, then ORDER_CREATED and EXECUTION_SIGNAL (both with setup_id + order_id) AFTER registry.create() in the user-required ordinal sequence, replacing the legacy free-text ORDER / EXECUTION SIGNAL logs. register() now dedupes BY NAME (one engine per stage), so a second register(ExecutionEngine()) is a no-op. Backtester: consume-exactly-once (fills only a registry-PENDING order; FILLED/terminal can never fill again), entry validation (candle.low <= entry <= candle.high, inclusive), a persistent limit-order model (a pending order fills the FIRST candle that trades through its entry, even a later one; no touch => ORDER_EXPIRED after MAX_WAIT_BARS, permanently unfillable), and ORDER_FILLED logged with setup/order/trade ids. TradeSimulator carries setup_id/order_id onto the open Trade and logs TRADE_CLOSED with the full identity chain at the single close choke point shared by all three modes. PaperTradingEngine and BrokerEngine consume PENDING orders through the SAME registry (mark_filled + ORDER_FILLED), so Paper/Live inherit the identical lifecycle and cannot double-fill either. Identity reaches the booked Trade: setup_id/order_id/trade_id on core/backtesting/trade.py. config/risk_settings.py adds MAX_WAIT_BARS = 30. Removed the redundant register() calls + unused imports in tests/test_backtester.py and examples/test_validation.py, test_position_manager.py, test_portfolio_backtester.py, test_performance_dashboard.py, test_performance_analytics.py, test_paper_trading.py, test_live_broker.py. NEW tests/test_execution_lifecycle.py -- 19 stdlib-only tests proving order-registry duplicate blocking + id formats + consume-exactly-once + expiry, engine idempotency (same setup processed twice -> exactly one order), RiskEngine-not-run-twice, execution-signal-cleared, pipeline name-dedupe, backtester consume-once, no fill without entry touch, fill on LATER touch, inclusive integer boundaries, one fill only, terminal order unfillable after expiry, the full setup->order->trade identity chain, max-1 event counts (SETUP_ACCEPTED / ORDER_CREATED / EXECUTION_SIGNAL / ORDER_FILLED / TRADE_CLOSED) across a multi-candle replay, and a 30-bar identical-world regression (exactly one order + one trade). Proof: compileall clean; full suite 370/370 green (351 + 19 new, zero existing-test changes). Docs: import_manifest.md added the EXECUTION LIFECYCLE section (STATUS 99; AST-verified new imports order_registry->config.risk_settings, backtester/paper/broker/pipeline_context/decision_engine/trade_simulator edges) + header refresh; project_manifest.md flips OrderRegistry (NEW active) and documents the lifecycle on the Stage components; the pipeline register() name-dedupe keeps PIPELINE_CONTEXT_OWNERSHIP unchanged (order_registry is session state on PipelineContext, same class of state as account/decision, and IS part of the documented reset surface).

100. Pending Order Integrity (Phase 4D -- user-selected after STATUS 99; bar-anchored fill / invalidation / expiration for working orders, replacing the call-count aging and fixing the same-candle look-ahead). The Phase 4C model aged pending orders by ORDER-COUNT (OrderRegistry.advance() bumped wait_bars EVERY candle, including the creation candle, so a brand-new order counted as already old), ran expiry BEFORE the candle's fill check (an order whose entry was touched on its expiry candle expired without ever getting its last chance to fill), allowed a fill on the creation candle from that candle's own intrabar range (a same-candle look-ahead -- the signal only exists at the candle's close), and had NO invalidation state (a structural stop breach was indistinguishable from an expiration). FIX, three parts. (1) BAR METADATA on OrderIntent: created_bar/created_timestamp stamped by registry.create(); eligible_from_bar = created_bar + ENTRY_DELAY_BARS (default 1 -- the earliest bar an order may fill, killing the look-ahead); expires_at_bar = eligible_from_bar + MAX_WAIT_BARS; filled_bar / terminal_bar / waited_bars / min_price_since_creation / max_price_since_creation / invalidation_level / invalidation_price. (2) ORDER REGISTRY: create(order, bar=None, timestamp=None) stamps the eligibility window at first registration; advance(bar=None, timestamp=None) EXPIRES a PENDING order only when bar >= expires_at_bar (bar-anchored; corner: NO expiry is possible before the expiry bar, the fill's last chance is the EXPIRY candle because advance() runs AFTER the fill/invalidation checks); invalidate(order, reason, bar, price, level) adds the NEW terminal state INVALIDATED -- a thesis break (bullish: candle.low <= stop_loss; bearish: candle.high >= stop_loss) is NOT an expiration and is logged ORDER_INVALIDATED with reason/price/invalidation_level; new expired()/invalidated() filters. (3) BACKTESTER per-candle order (Phase 4D STEP 4): update pending (roll min/max since creation) -> skip ineligible (bar < eligible_from_bar) -> invalidation before fill (a candle that BOTH breaks the stop and reaches the entry is invalidated -- conservative; ambiguity resolves against the fill) -> entry touched (low <= entry <= high, inclusive) -> EXACTLY ONE fill via mark_filled (single-position model) -> THEN advance() for expiry -> (next candle) pipeline publish -> ExecutionEngine emits the ranked batch (top MAX_PENDING_ORDERS by score, tie-broken by registration order, capped by the registry's remaining pending slots, every already-ordered setup skipped) as context.execution_signals; RiskEngine order-mints ONE order per emitted signal under (a) the one-setup == one-order registry re-check, (b) the MAX_PENDING_ORDERS slot cap, and (c) the MAX_TOTAL_EXPOSURE_PCT aggregate-notional ceiling vs current equity (ORDER_SKIPPED_EXPOSURE info log; accepted setups queue, never silently dropped); context.orders (list) + context.order (first). Diagnostics upgraded: ORDER_EXPIRED now carries setup_id/order_id/created_bar/eligible_from_bar/expired_bar/waited_bars/max_wait_bars/entry/min_price_since_creation/max_price_since_creation; ORDER_FILLED now carries created_bar/filled_bar/waited_bars/entry/candle_low/candle_high (proving low <= entry <= high). Legacy scripted orders without an order_id stay same-candle by contract; Paper/Live are unchanged in spirit (real-time fill-on-signal through the SAME registry.mark_filled path, no replay eligibility delay). config/risk_settings.py adds ENTRY_DELAY_BARS = 1, MAX_PENDING_ORDERS = 8 (execution-CAPACITY default, not a strategy threshold; 3 was the initial default and starved the funnel), MAX_TOTAL_EXPOSURE_PCT = 25.0 (a runaway-pending backstop that must clear the 8-slot x ~2.5x-equity natural notional, so it never acts as a per-order gate -- the initial 10.0 default silently gated accept-ready setups; 25.0 produced 0 exposure skips on the regression), MAX_WAIT_BARS = 30 unchanged. NEW tests: tests/test_execution_lifecycle.py +14 (new-order-can't-expire-same-bar, becomes-eligible-next-bar, waits-until-entry-touched, fills-when-entry-inside-candle-range, does-not-fill-when-entry-not-reached, expires-exactly-at-expiry-bar, fill-prevents-later-expiration, terminal-cannot-fill-after-expiry bar-based, invalidates-before-expiration, invalidation-precedes-fill-on-same-candle, multiple-pending-respect-limit, multiple-pending-both-sit-pending, created-bar-metadata-correct, order-created-to-expired-log-chain); two legacy tests updated to bar-anchored semantics (the step-1 trace proved entry-boundaries far candle now legally breaches the stop -> INVALIDATED). Proof: compileall clean; full suite 384/384 green (370 + 14 net; zero non-lifecycle test changes). Docs: import_manifest.md added the PENDING ORDER INTEGRITY section (STATUS 100) + header refresh; STATUS 99's advance() text is superseded by the bar-anchored advance() documented here; project_manifest.md marks Pending Order Integrity Active and updates the pipeline order note (STEPS 4-8); PIPELINE_CONTEXT_OWNERSHIP unchanged (execution_signals/orders are per-cycle slot fields, cleared in reset_cycle(), same class of state as execution_signal/order). 5000-bar regression (tests/test_backtester.py, live BTCUSDT 1m, network): 5000 bars; 127 orders created; 121 EXPIRED -- EVERY one a clean no-touch (verified min/max_price_since_creation vs entry field-by-field on the ORDER_EXPIRED diagnostics) -- 6 INVALIDATED, 0 FILLED, 0 trades. The 0-fill outcome is the honest result of the Phase 4D no-look-ahead + bar-anchored window on this falling window: Phase 4C's 8 fills were same-candle fills (the signal candle traded through its own entry); Phase 4D bans that look-ahead, and no entry was ever re-touched inside a free-slot 30-bar window. The fill/invalidation/expiry mechanism itself is proven by the TestPendingOrderIntegrity suite (exact synthetic fills with bar metadata); the 8-knob sweep (3 -> 8 slots, exposure 10 -> 25) proved the caps were not the binding constraint (127 created/0 exposure skips at full capacity, still 0 fills on this window).101. Economic Setup Deduplication + Lifetime Excursion (Phase 4E -- user-selected after STATUS 100). TWO defects surfaced in the STATUS 100 ledger. (a) FROZEN EXCURSIONS: while a trade was OPEN the backtester's pending-order pass was skipped entirely -- _execute_signal early-returned the moment current_trade was not None -- so a working order's min/max_price_since_creation froze at its first-bar values and ORDER_EXPIRED could misreport the true window. (b) DUPLICATE ECONOMICS: the live 6000-bar run minted SEPARATE pending orders for structurally-distinct order blocks with IDENTICAL trade economics (OB-954/OB-956 and the OB-928..956 family of 77616.00/77631.50/77415.80 variants) -- MAX_PENDING_ORDERS slots spent on ONE market idea. FIX, three parts. (1) PHASE 4E LIFETIME EXCURSION on OrderIntent (min_price_since_creation/max_price_since_creation REMOVED): min_low_since_creation/max_high_since_creation over ELIGIBLE bars only (creation candle contributes nothing), bars_pending = eligible bars spent INCLUDING the expiry bar as the fill's last chance (MAX_WAIT=30 -> bars_pending=31), entry_distance_from_nearest_price (0.0 when min_low <= entry <= max_high else min distance to either extreme). Backtester Step 4: skip ineligible -> eligible-only excursion roll (bars_pending += 1, init then roll min_low/max_high) -> invalidation (structural stop breach wins over entry touch) -> entry reached (low <= entry <= high) -> EXACTLY ONE fill gated only on the single-position model; the pending pass now runs EVERY candle open position or not, and after a fill the loop CONTINUES so the remaining pending orders still roll/invalidate that candle (the anti-freeze regression fix). ORDER_EXPIRED re-logged with the full excursion window + entry_distance_from_nearest_price (also stamped on the order); new ledger metrics pending_orders_average/pending_orders_max. (2) ECONOMIC IDENTITY + DEDUP: trade_setup_builder stamps structural_id (=setup_id) + economic_fingerprint on every SetupCandidate (setup_candidate carries structural_id/economic_fingerprint/is_economic_duplicate/economic_canonical_id/observed_bar); NEW core/setup/economic_setup_registry.py -- fingerprint_of() builds [symbol]-[timeframe]-[direction]-E-entry-S-stop-T-target snapped to the ECONOMIC_TICK_SIZE=0.5 grid (idempotent; SetupCandidate has no symbol/timeframe so the builder passes them, OrderIntent carries both and derives at runtime); EconomicSetupRegistry.observe(setups, order_registry, bar) runs EVERY candle as the ExecutionEngine chokepoint BEFORE the pending-slot cap: (i) drop structurally already-ordered, (ii) suppress fingerprints already live as PENDING (active-idea dedup), (iii) collapse identical-fingerprint candidates within the candle to the highest-ranked canonical, (iv) cluster near-identical zones when entry AND stop AND target are each within tolerance = max(ECONOMIC_TICK_SIZE x ECONOMIC_CLUSTER_TICKS [0.5x8=4.0 at ~110], price x ECONOMIC_CLUSTER_PCT [0.1%], ATR x ECONOMIC_CLUSTER_ATR_FRACTION [0.0 off]) -- NO hard-coded BTC point distances, entry 77616 vs 77620 clusters by design -- and (v) rank canonicals deterministically (-score, -confidence, -liquidity_alignment, -rr, -observed_bar, structural_id ascending), never random; duplicates flagged is_economic_duplicate + economic_canonical_id. ExecutionEngine calls observe() as the chokepoint so the cap is applied AFTER clustering (duplicates can never starve independent ideas). RiskEngine stamps structural_id + economic_fingerprint onto the OrderIntent at mint time. PipelineContext owns the persistent economic_registry (created in __post_init__, re-created on reset(), NOT cleared by reset_cycle() -- same class of session state as order_registry). config/risk_settings.py adds ECONOMIC_TICK_SIZE=0.5, ECONOMIC_CLUSTER_TICKS=8, ECONOMIC_CLUSTER_PCT=0.001, ECONOMIC_CLUSTER_ATR_FRACTION=0.0; strategy thresholds, MAX_PENDING_ORDERS (8) and MAX_WAIT_BARS (30) are UNCHANGED (no tuning -- objective is independence of opportunities, not more trades). (3) TESTS: tests/test_execution_lifecycle.py +5 TestOrderExcursionTracking (tracks-minimum-low/maximum-high-across-multiple-bars, each-pending-order-has-independent-excursion-data, expiration-log-uses-lifetime-excursion, entry-touch-is-detected-before-expiration); two legacy multi-pending tests moved to a NEW distinct world (the old near-identical world 110/100/130 vs 109/100.5/130 CLUSTERS into one canonical by design under 4E -- canonical wins on reward/risk 2.47 > 2.0 -- so it can no longer demonstrate independent slots; the distinct world uses far-apart zones -- entry 110 vs 120, stop 100 vs 109, target 150 for both -- that stay independent); NEW tests/test_economic_setup_dedup.py 6 (same-trade-economics-different-ob-ids -> one setup; same-entry/stop/target -> ONE pending order end-to-end; nearby-entries-cluster-when-threshold-allows; independent-setups-do-not-cluster; cluster-selects-highest-priority-setup; pending-order-limit-applies-after-clustering). Proof: compileall clean; full suite 395/395 green (384 + 11 new; the two multi-pending re-fixures are the only existing-test edits -- no behavior regression, 4E's clustering contracts to the best setup, not the first structural discovery). Docs: import_manifest.md added the ECONOMIC SETUP DEDUPLICATION section (STATUS 101, AST import census: trade_setup_builder + pipeline_context import economic_setup_registry, execution_engine/risk_engine duck-type via context/signal) + header refresh + the stale Phase 4D min/max_price_since_creation references updated to the Phase 4E lifetime excursion fields; project_manifest.md marks EconomicSetupRegistry Active (STATUS 101), ExecutionEngine + backtester STATUS 101; PIPELINE_CONTEXT_OWNERSHIP unchanged (economic_registry is session state beside order_registry). 5000-bar regression (tests/test_backtester.py, live BTCUSDT 1m, network): 5000 bars; 423 structural setups discovered collapsed to 73 distinct economic ideas (397 duplicates suppressed -- the OB-968/OB-970 identical-economics pair now mints exactly ONE order, closing the STATUS 100 OB-954/OB-956 repeat-ordering defect); 2 clusters formed; 83 orders created (vs 127 without dedup at identical capacity), 0 FILLED / 78 EXPIRED / 5 INVALIDATED, avg pending 0.5 / max pending 7, 0 trades -- the same honest no-look-ahead result as STATUS 100, now at full execution capacity with per-independent-idea ordering. Expected note: ECONOMIC_CLUSTER_PCT dominates at BTC-scale prices (~0.1% of 77000 > 8x0.5 ticks); per spec, configurable, no hard-coded points.
101. Economic Setup Deduplication (Phase 4E -- user-selected after STATUS 100).
Two defects surfaced in the STATUS 100 ledger: (1) FROZEN EXCURSIONS -- while a
trade was OPEN the backtester skipped the pending-order pass entirely, so a
working order's min/max_price_since_creation froze at first-bar values and
ORDER_EXPIRED misreported the true window; (2) DUPLICATE ECONOMICS -- the live
6000-bar run minted SEPARATE pending orders for structurally-distinct order
blocks with IDENTICAL trade economics (the OB-954/OB-956 pair and the
OB-928..956 family), spending MAX_PENDING_ORDERS slots on ONE market idea.
FIX: (a) core/risk/order_intent.py replaces the frozen creation-candle
excursions with lifetime eligible-only fields -- min_low_since_creation /
max_high_since_creation (the creation candle contributes NOTHING),
bars_pending (eligible bars INCLUDING the expiry bar, the fill's last chance:
MAX_WAIT_BARS=30 -> bars_pending=31) and entry_distance_from_nearest_price
(0.0 when min_low <= entry <= max_high, else min distance to either extreme);
(b) NEW core/setup/economic_setup_registry.py -- the second deduplication
layer keyed on a tick-normalized economic_fingerprint (symbol, timeframe,
direction, entry/stop/target buckets, ECONOMIC_TICK_SIZE) that collapses
IDENTICAL economics (whether from a live pending order or within the candle)
and CLUSTERS near-identical zones within configurable thresholds, then ranks
one canonical representative per zone by score -> structural gate -> creation;
execution_engine routes every accepted setup through observe() BEFORE the
pending-slot cap, so capacity is spent on INDEPENDENT opportunities; the
registry also marches as a SETUP state machine (NEW -> ACCEPTED ->
ORDER_CREATED -> FILLED / INVALIDATED / EXPIRED with explicit CANCEL) and
ANY order > MAX_WAIT_BARS forces expiry -- live orders NEVER linger; (c)
backtesting/backtester.py runs the pending-order pass EVERY candle -- open
position or not -- with the eligible-only excursion roll, invalidation on a
structural stop breach BEFORE the fill check, exactly one fill when
low <= entry <= high, then advance() to expire on the expiry bar, so a
pending order's excursion window spans its WHOLE eligible lifetime.
Proof: new tests/test_economic_setup_dedup.py (11 stdlib-only contract tests:
different-ob-ids -> one setup; same entry/stop/target -> ONE pending order
end-to-end; nearby-entries cluster when the threshold allows; independent
setups NEVER cluster; a cluster selects the HIGHEST-priority setup; the
pending-order limit applies AFTER clustering). 5000-bar regression (live
BTCUSDT 1m): 423 structural setups discovered collapsed to 73 distinct
economic ideas (397 duplicates suppressed); 2 clusters formed; 83 orders
created (0 FILLED / 78 EXPIRED -- every one a clean no-touch per the new
lifetime excursion fields -- / 5 INVALIDATED); avg pending 0.5, max pending
7; 0 trades -- the same honest no-look-ahead result as STATUS 100 at full
execution capacity with per-independent-idea ordering. Full suite 395/395
green (384 + 11 new), compileall clean.

102. Entry Feasibility, Retracement Analysis and Multi-Mode Entry (Phase 4F --
user-selected after STATUS 101). Builds on the Phase 4E economic layer with a
purely DIAGNOSTIC measurement of every accepted setup's entry and what price
ACTUALLY does after, then sponsors the multi-mode entry architecture without
changing a single live threshold or enabling any new entry model (no strategy
change, no order-expiration increase, no market entries). STEP 1-2 -- ENTRY
FEASIBILITY: NEW core/setup/entry_feasibility.py measures ONE quantity
(|entry - creation price|) on FOUR normalization axes (absolute / percent of
price / ATR_14 multiples / ticks, ECONOMIC_TICK_SIZE) and classifies the
result IMMEDIATE / NEAR / RETRACE / DEEP_RETRACE / TOO_FAR against
configurable ATR-normalized thresholds (0.10/0.35/0.75/1.50 default) -- never
a symbol-specific point distance. TradeSetupBuilder stamps
observed_price / atr / entry_mode / entry_feasibility on every candidate (NONE
influence accept/avoid). STEP 3-5 -- RETRACEMENT TRACKING: NEW
core/setup/entry_tracker.py measures, from the bar AFTER the creating candle
only (no look-ahead), the retracement toward the entry (fraction [0,1], capped
approach extreme), entry touch (low <= entry <= high), bars until the nearest
approach / the touch, the largest continuation in the TARGET direction, the
distance still remaining at expiration, and MISSED_CONTINUATION (entry never
touched yet price ran >= MISSED_CONTINUATION_TARGET_FRACTION=0.5 of the way to
the target inside a ENTRY_TRACKING_WINDOW_BARS=60 window); FILLED /
INVALIDATED freeze, EXPIRED snapshots at the expiry bar then keeps rolling the
full window so the continuation analysis is honest. STEP 6 -- MULTI-MODE ENTRY
ARCHITECTURE: NEW core/execution/entry_mode.py introduces the entry-mode
value (LIMIT_RETEST baseline; ACTIVE_ENTRY_MODES config) carried VERBATIM
SetupCandidate -> OrderIntent -> Trade -> ledger/report with zero behavioral
effect in Phase 4F; the backtester fill gate is mode-aware (an order whose
mode is not in ACTIVE_ENTRY_MODES stays parked -- fills refused, excursions /
invalidation still roll) -- a future MARKET_CONFIRMATION mode needs only a
config flip, no structural change. STEP 8 -- PENDING CAPACITY POLICY:
MAX_PENDING_ORDERS_TOTAL=8 / PER_SYMBOL=8 / PER_DIRECTION=4 /
PER_CLUSTER=1 replace the single flat cap; the per-cluster=1 rule is enforced
STRUCTURALLY by the economic registry (one canonical per zone) and the
per-direction budget is enforced in BOTH ExecutionEngine and RiskEngine, so a
row of same-direction ideas can never hoard every slot. STEP 9 -- ECONOMIC
RE-ENTRY COOLDOWN: EconomicSetupRegistry gains lifecycle states (ACTIVE /
COOLDOWN) and mark_terminal / sync_lifecycles (called every candle): an order
that FILLS clears the fingerprint (no cooldown after a realized fill), while
EXPIRED / INVALIDATED put the fingerprint into a REENTRY_COOLDOWN_BARS=30
window during which a structurally-fresh SAME-economics discovery is
suppressed (reentry_cooldown_suppressed counter) instead of re-minting -- a
NEW structural setup of the same economics is legal again the moment the
cooldown lapses (time-based only). STEP 10 -- TEST PROOF: NEW
tests/test_entry_feasibility.py (17 stdlib-only tests): entry distance on all
four axes; ATR-normalized distance scaling; classification boundaries
(inclusive) + custom thresholds; bullish AND bearish retracement tracking with
touch bars and the capped-approach math; retracement fraction tracking; missed
continuation detection + the two honest contrasts (stop-ward grind clears it;
an entry touch -- even once -- clears it); the no-leak proof (the identical
world run with ENABLE_ENTRY_DIAGNOSTICS False is outcome-identical, the tracker
simply records nothing); entry mode preserved SetupCandidate -> OrderIntent ->
Trade; the per-cluster=1 structural rule + the per-direction budget (a second
same-direction independent idea queues even at cheap totals); expired-idea
cooldown (ONE order ever + reentry_cooldown_suppressed >= 1, with a
zero-cooldown control that genuinely re-mints proving the suppression is the
cooldown); and a short cooldown that frees a genuinely NEW structural setup
of the same economics at exactly bar+N. Full suite 412/412 green (395 + 17
new), compileall clean. STEP 11 -- 5000-BAR REGRESSION (live BTCUSDT 1m,
tests/test_backtester.py, which now also prints the Re-Entry Cooldown
Suppressions ledger line, the Max Pending Explanation with the max bar and
its per-direction breakdown, the Orders By Entry Mode ledger, and the full
ENTRY FEASIBILITY REPORT in ALL / BULLISH / BEARISH blocks): 961 structural
setups discovered collapsed to 110 distinct ideas (762 duplicates suppressed);
4 clusters; 112 orders created (2 FILLED / 102 EXPIRED / 8 INVALIDATED);
Re-Entry Cooldown Suppressions 42; avg pending 0.66, max pending 4 (first
reached at bar 615 -- 4 BULLISH, 0 BEARISH: the per-direction budget binding,
not the total); all 112 orders LIMIT_RETEST (ACTIVE_ENTRY_MODES single).
ENTRY FEASIBILITY REPORT: 250 setups tracked; 248 ENTRY_TOO_FAR / 1
ENTRY_IMMEDIATE / 1 ENTRY_RETRACE; entries reached 3 / not reached 247;
avg entry distance 571.13 pt (median 541); avg ATR-distance 289.6 (median
60.0 -- the mean is skewed by dead-minute candles where the 1m ATR collapses
to $0.2-1.5 while the entry stays ~$500 away: honestly hundreds of ATRs
unreachable); avg max retracement toward the entry 0.2143 (21%); avg distance
still remaining at expiration 478.7 pt; MISSED_CONTINUATION 229 (entries never
touched while price ran half-way-or-more to its target) -- the quantified,
evidence-backed case for why the Phase 4F LIMIT_RETEST baseline almost never
fills on 1m BTC and why a future confirm-then-enter mode is the natural next
extension (still diagnostic-only here). Trades 2. NOTE: the ledger does NOT
compare numerically to the Phase 4E STATUS 101 regression because the two
runs consumed DIFFERENT live data windows (structural discoveries 423 -> 961
are window drift, not a regression); the cooldown's suppressing effect is
proven internally (42 re-entry suppressions; the cold cooldown test's
zero-cooldown control) and by the dedicated deterministic tests. No Phase 4F
change altered a Phase 4E threshold, an order expiration, or the entry model.

103. Structural Zone Freshness, Entry Eligibility and Canonical Setup
Generation (Phase 4G -- user-confirmed baseline config, ordered NOT to
tune this phase). STEP 1-3 -- ZONE AGE + FRESHNESS: OrderBlock gains the
at-creation snapshot (origin_bar / created_bar / age_bars / age_time_seconds
/ freshness / distance_from_current_price(+_atr) / mitigation_status /
last_tested_bar(+_timestamp)); OrderBlockScanner measures age as the DIRECT
current - origin bar count (never a counter -- the scanners re-derive the
window every candle, so only a measurement survives) by backing up to the
origin candle; classify_freshness derives NEW/FRESH/ACTIVE/TESTED/MITIGATED/
STALE/INVALIDATED (MAX_ORDER_BLOCK_AGE_BARS=500 global, per-timeframe map
override-able; FRESH_ORDER_BLOCK_AGE_BARS=5). STEP 4/7 -- STRUCTURAL vs
TRADE ELIGIBILITY SPLIT: NEW core/order_blocks/zone_freshness.py
evaluate_entry_eligibility returns (structurally_valid, trade_eligible,
primary_reason, diagnostics); structurally_valid is INDEPENDENT of trade
eligibility (a stale but unbroken zone stays valid); blocking reasons
INVALIDATED_STRUCTURE / ALREADY_MITIGATED / STALE_ZONE /
TOO_FAR_FROM_MARKET (entry distance > MAX_LIMIT_ENTRY_DISTANCE_ATR=30.0
x ATR) / INSUFFICIENT_RISK_WIDTH (entry-stop < MIN_RISK_WIDTH_ATR=0.10
x ATR; binds on ALL paths incl. risk<=0; ATR gates pass through at atr<=0
-- harness convention); WEAK_DISPLACEMENT / TOO_MANY_TOUCHES
(MIN_ORDER_BLOCK_DISPLACEMENT=50 / MAX_ORDER_BLOCK_TOUCHES=3) are
diagnostic-only in the baseline -- computed + reported, never blocking;
conservative priority for ties. STEP 5-6 -- Consumer agnostic of the
split (used by DecisionEngine + reports). STEP 8 -- ALL-PATHS MIN-RISK
DEFENSE: RiskEngine applies the SAME MIN_RISK_WIDTH_ATR gate on every
order-minting path (even signals that bypassed the builder; legacy
OrderIntent signals carry no ATR axis and pass through). STEP 9-10 --
STRUCTURAL ZONE CLUSTERING: cluster_structural_zones collapses
same-direction blocks whose entry AND stop are both inside the Phase 4E
economic tolerance (one execution surface == one cluster) into ONE
canonical zone (freshest -> strongest displacement -> highest score ->
least-touched -> widest stop -> lowest index, Phase 4E parity OB-5 beats
OB-6), stamps cluster_id / is_canonical / canonical_zone_id; TradeSetupBuilder
clusters BEFORE candidate generation (ENABLE_STRUCTURAL_CLUSTERING=True)
and candidates come only from canonical zones. STEP 11-12 -- REPORTING:
NEW core/setup/zone_eligibility.py (first-appearance-per-structural_id
dedup, exactly the EntryTracker rule) logs every canonical zone --
eligible or rejected -- with its at-creation snapshot, and the regression
prints ORDER BLOCK FRESHNESS + ENTRY ELIGIBILITY reports in ALL/BULLISH/
BEARISH (by_reason, by_freshness, by_age_bucket 0-5/6-15/16-30/31-60/
61-120/120+). DecisionEngine rejects trade_eligible=False candidates
outright (SETUP_REJECTED reason=<reason>, deduped per (reason,
fingerprint); the reason survives to the report). STEP 13 -- TEST PROOF:
NEW tests/test_zone_freshness.py (19 stdlib-only tests): the e2e four-
engine chain over hand-seeded zones proves fresh zone -> order, stale ->
0 orders + STALE_ZONE while STILL structurally_valid, far -> 0 orders,
near -> order, thin stop -> 0 orders + INSUFFICIENT_RISK_WIDTH, the
RiskEngine defense-in-depth gate (wide patched floor kills a thin stop
but lets a normal stop through), identical twins -> ONE cluster + ONE
order, canonical = fresher/stronger twin, distinct zones never merge,
only entry-eligible zones mint setups, rejection reasons preserved, the
SETUP_REJECTED dedup, plus TWO real-pipeline no-leak proofs over the
synthetic feed (zone age grows exactly with the window on every re-mint;
stamped freshness consistent with age + structure state, origin never in
the future, age-time >= 0, STALE exactly iff age > cap). The four Phase
4E/4F tests that asserted the PRE-clustering ordering were updated to the
Phase 4G contract: identical-geometry twins now collapse at the BUILDER,
so the identical-economics "both setups surface" e2e scenarios assert ONE
canonical candidate + ONE order, and the re-entry-cooldown tests exercise
Phase 4F STEP 9 at the EconomicSetupRegistry boundary (direct-API
suppression during the window, legal again the moment it lapses, control
with cooldown off) -- the identical-twin e2e cooldown path is structurally
superseded by clustering. Full suite 431/431 green (412 + 19 new),
compileall clean. STEP 14 -- 5000-BAR REGRESSION (same live BTCUSDT 1m
tests/test_backtester.py, now also printing the two Phase 4G report
blocks), BEFORE (Phase 4F, recorded) vs AFTER (Phase 4G, run today):

  Metric                        BEFORE (4F)     AFTER (4G)
  Structural setups discovered  961             101 (structural dedup)
  Economic duplicates           762             68
  Distinct ideas                110             21
  Clusters formed               4               0
  Orders created / filled /     112 / 2F /      22 / 2F /
    expired / invalidated       102E / 8I       16E / 4I
  Setups tracked (orders)       250             22
  ENTRY_TOO_FAR share           248/250 (99.2%) 20/22 (90.9%)
  Avg entry-dist ATR            289.6           14.54
  Median entry-dist ATR         60.0            14.44
  Missed continuations          229             19
  Re-Entry cooldown suppr.      42              11
  Avg pending / max pending     0.66 / 4        0.11 / 3

  Entry-eligible zones (Phase 4G funnel): 2424 canonical zones logged
  (206 distinct ideas), 294 trade-ELIGIBLE (the ones the budget/cooldown
  funnel then narrowed to 22 orders) and 2130 trade-INELIGIBLE
  (STALE_ZONE 793, TOO_FAR_FROM_MARKET 1104, INSUFFICIENT_RISK_WIDTH
  233); every one of the 2424 structurally VALID (0 invalid -- the
  structural/trade split held); 355 structural duplicates suppressed by
  STEP-9 clustering; diagnostic Wide-displacement none, Too-many-touches
  19 (reported, never blocking); freshness FRESH 14 / ACTIVE 1617 /
  STALE 793; age buckets 0-5:14, 6-15:60, 16-30:86, 31-60:153,
  61-120:185, 120+:1926; avg zone age 382 bars; all 22 orders
  LIMIT_RETEST (ACTIVE_ENTRY_MODES single). The order drop is the
  INTENDED baseline gate, not tuning: 88% of canonical zones fail an
  entry-eligibility gate this phase, exactly as ordered (no threshold was
  raised and no entry mode enabled); WHERE to tune (if at all) is
  deferred until the user reviews this table. The 4F-to-4G comparison is
  on the same symbol/timeframe/resolution methodology but a slightly
  different live window (the registry numbers shift with the market;
  the internal funnel proportions are the meaningful comparison).

104. ENTRY MODEL REACHABILITY & SHADOW COMPARISON (Phase 4G extension --
diagnostic
only: NOTHING executable changed, no threshold moved, LIMIT_RETEST remains
the ONLY mode that can mint/fill an order; the user ordered that
MARKET_CONFIRMATION may become an executable mode ONLY after reviewing
this comparison report). QUESTION: is QuantitativeEngine's structural
analysis bad, or is it trying to trade a RETEST strategy in a market that
frequently CONTINUES without providing the retest? STEP 1 -- SHADOW MODEL:
NEW core/setup/entry_shadow.py (ShadowFill + EntryShadowState dataclasses +
EntryShadow observe/advance/_roll/_settle/report + format_shadow_report).
Authoritative entry-model trigger contract: LIMIT_RETEST = candle trades
through E (bull low <= E <= high), stop breach checked BEFORE fill (the
backtester's step-3 before-step-4 order -- invalidation beats a same-bar
fill); MARKET_CONFIRMATION (shadow) = candle reaches E AND closes beyond
it in the trade direction (bull close >= E / bear close <= E), enters at
that candle's CLOSE -- can never fill a stop-ward sweep that closes on
the wrong side; BREAKOUT_CONTINUATION (shadow) = candle EXCEEDS E on the
trade side AND closes beyond it (bull high > E and close > E / bear low
< E and close < E) -- anchored on the OB reference level E (OrderBlock.
entry), NOT a running creation-bar extreme; each model triggers
independently (no mutual exclusion); SHADOW_ENTRY_MODES gates which
shadows are measured, LIMIT_RETEST always measured. Resolution mirrors
trade_simulator: SL checked before TP per bar (bull low <= stop -> LOSS),
same-bar both-hit = LOSS; MAE/MFE measured from the FIRST bar AFTER the
entry bar (entry bar excluded) and capped at stop/target on the
resolution bar; an UNTRIGGERED model is never resolved (the resolution
step skips not-yet-triggered states); _safe_div treats None as 0.0
immediate-stop fills). STEP 2 -- POPULATION + CONTEXT: builder
observe() takes every trade-eligible canonical candidate, deduped on
first appearance per structural_id (identical to zone_eligibility, so the
population == the trade_eligible count, 304 here); order context
(order_id / created_bar / expires_at_bar) attached once from the registry;
reached_within_expiry decided at settle against the REAL 30-bar expiry
(default horizon creation+1+MAX_WAIT_BARS when unminted); window =
ENTRY_TRACKING_WINDOW_BARS (60). STEP 3 -- WIRING: entry_shadow on
PipelineContext (_new_entry_shadow factory + reset()); TradeSetupBuilder
calls shadow.observe() beside elig_log.observe(); Backtester calls
entry_shadow.advance(candle, bar, order_registry) every candle beside
entry_tracker.advance (both session states); tests/test_backtester prints
ENTRY MODEL COMPARISON REPORT blocks ALL/BULLISH/BEARISH gated on
ENABLE_ENTRY_SHADOW. STEP 4 -- CONFIG (config/risk_settings.py, shadow
block): ENABLE_ENTRY_SHADOW = True; SHADOW_ENTRY_MODES =
("MARKET_CONFIRMATION", "BREAKOUT_CONTINUATION"); reuses MAX_WAIT_BARS=30 /
ENTRY_TRACKING_WINDOW_BARS=60 / MISSED_CONTINUATION_TARGET_FRACTION=0.5.
STEP 5 -- TEST PROOF: NEW tests/test_entry_shadow.py (20 stdlib-only
tests): per-model triggers, invalidation-before-fill, bearish mirrors,
SL-before-TP same-bar resolution, MFE/MAE caps, MAE excludes the entry
bar, UNRESOLVED settle, missed-continuation (gap-runner), ATR-vs-expiry
buckets + negative-correlation scenario, default horizon, population ==
eligibility trade_eligible, order-context attach over a 63-candle world
reaching settle, SHADOW_ENTRY_MODES gating, byte-identical no-leak
fingerprints. Full suite 451/451 green (431 + 20), compileall clean.
STEP 6 -- 5000-BAR REGRESSION (same live BTCUSDT 1m; funnel this run: 98
structural setups / 68 econ dupes / 18 ideas / 0 clusters / 19 orders
(1F/16E/2I) / 11 cooldown suppressions / avg pending 0.1 max 3 at bar
1820 (3 bullish); 2235 canonical zones / 197 ideas / 304 trade-eligible
(561 STALE / 1139 TOO_FAR / 231 INSUFFICIENT_RISK_WIDTH; 341 structural
dups suppressed; freshness FRESH 12 / ACTIVE 1662 / STALE 561; age
buckets 0-5:12, 6-15:57, 16-30:83, 31-60:149, 61-120:185, 120+:1749; avg
zone age 351.94 bars); entry tracker 19 setups (1 IMMEDIATE / 18
TOO_FAR), 1 reached, avg entry dist 15.54 ATR med 14.535, missed 17.
DRIFT NOTE: the funnel shifted slightly vs STATUS 103 (19 vs 22 orders,
304 vs 294 eligible, 98 vs 101 structural, 2235 vs 2424 zones) on the
SAME source data -- window drift, not a regression; the STATUS 104 truth
is the run below.

ENTRY MODEL COMPARISON (ALL, 304 trade-eligible setups; window/expiry 60/30)

  Model                   Fills      Bars-to-entry    Entry dist      W/L/U        Missed cont.
  LIMIT_RETEST            8 (2.6%)   avg/med 4.5/4.5   1.47 ATR        0/8/0        284 (93.4%)
  MARKET_CONFIRMATION     0 (0.0%)   avg/med 0.0/0.0   0.00 ATR        0/0/0        292 (96.1%)
  BREAKOUT_CONTINUATION   292 (96.1%) avg/med 1.0/1.0  1.04 ATR        238/38/16     2

  BULLISH (141): LIMIT 8 fills (5.7%) ALL LOSS (MAE/MFE 0.23/0.0 ATR),
  MARKET 0, BREAKOUT 138 fills (97.9%) 110W/15L/13U. BEARISH (163):
  LIMIT 0 fills, MARKET 0, BREAKOUT 154 fills (94.5%) 128W/23L/3U.
  Breakout avg MAE/MFE 2.97/7.38 ATR (over the 292 triggered fills).

ATR-DISTANCE vs 30-BAR EXPIRY (ALL): correlation -0.31 (BULLISH -0.53;
BEARISH degenerate 0.0 -- zero bearish reaches ever). Avg entry distance
FILLED 1.47 ATR vs UNFILLED 16.69 ATR (BULLISH 1.47 vs 19.70). Buckets
(count, within-expiry): 0-1 ATR -> 4 (1); 1-2 -> 11 (7); 2-5 -> 5 (0);
5-10 -> 46 (0); 10-15 -> 87 (0); 15-30 -> 151 (0); 30+ -> 0. All 8 limit
fills arrived within the real expiry (1 + 7); a retest was NEVER reached
beyond ~2 ATR even inside the full 60-bar window; avg bars-to-entry 4.5
means the market retests promptly or not at all. BEARISH is worst: zero
retest reach at ANY distance in the whole run (163/163 never).

VERDICT: the user hypothesis is confirmed quantitatively -- 1m BTC
continues without retesting; a retest is rare (2.6% of eligible setups)
and every one of the 8 in-sample retest fills ended in a LOSS; a
close-beyond confirmation NEVER fired; a continuous-breakout capture fills
96% of eligible setups one bar out with a 78% in-sample win rate (238/304
wins). The binding constraint is ENTRY DISTANCE IN ATR, not the 30-bar
expiry: expiry bars only decide which surviving ~1-2 ATR retests fill;
beyond ~2 ATR a retest basically never occurs on 1m BTC. CAVEATS
(mandatory honesty): 0/8 limit fills is a tiny in-sample sample -- the
2.6% fill rate and 0/8 loss count are weak evidence, not a proof; the 78%
breakout win rate is a SHADOW/hypothetical number -- no slippage, no
fees, no capital/budget constraint; shadow limit fills (8) do NOT equal
real order fills (1) because the shadow walks all 304 eligible setups
over a 60-bar window while only 19 orders existed over the real 30-bar
expiry under the budget/cooldown funnel. DECISION DEFERRED: no threshold
may move and no entry mode may be enabled until the user reviews this
table.

105. CAUSAL BREAKOUT CONTINUATION VALIDATION (Phase 4H -- diagnostic only:
NOTHING executable changed, no threshold moved, LIMIT_RETEST remains the
ONLY mode that can mint/fill an order, and BREAKOUT_CONTINUATION stays a
shadow until the user reviews this report -- the user ordered the phase to
run under the CONSERVATIVE intrabar policy BEFORE it may create real
orders). QUESTION: does the STATUS 104 breakout win rate survive STRICT
causal execution -- a frozen setup, a trigger decided only at the trigger
candle's close, an entry at the OPEN of the NEXT bar, and deterministic
intrabar SL/TP resolution -- when, as STATUS 104 noted, "a high win rate
is cheap to fake (enter where you can already see price went)"?
STEP 1 -- CAUSAL RULES (NEW core/setup/causal_validation.py: CausalValidator
+ CausalValidationState + format_causal_report): RULE 1 FREEZE AT
CREATION -- observe() snapshots direction/entry/stop/target/identity/
creation state and never reads the setup again; the setup object and any
candle seen after can be mutated freely with no effect (test-proven).
RULE 2 TRIGGER AT CLOSE -- BULLISH high > E AND close > E / BEARISH low < E
AND close < E, decided from ONLY the trigger candle's range + close
(breakout_trigger_bar / _trigger_close recorded); the structural stop
breach is checked BEFORE the trigger on every candle (the backtester's
step-3-before-step-4 order), so a same-bar stop breach invalidates the
idea and no trigger fires. RULE 3 NEXT-BAR EXECUTION -- a trigger at bar N
is entered at the OPEN of bar N+1 (the first price reachable after the
trigger close), a market fill that executes even when N+1 opens against
the position; a trigger on the last in-window bar has no executable next
bar and counts as a trigger without an entry. RULE 4 DETERMINISTIC
INTRABAR RESOLUTION -- when one candle spans both stop and target the
favorable outcome is never assumed: CONSERVATIVE (stop first -> LOSS, the
Phase 4H PRIMARY) / OPTIMISTIC (target first -> WIN) / EXCLUDE (dropped
from W/L accounting); every trade records the CONSERVATIVE outcome plus an
ambiguity flag, so all three policies render from ONE walk; MAE/MFE
include the entry bar's post-open range (a real open fill's exposure) and
are floored at the stop/target levels; R multiples: WIN =
reward/risk from the ACTUAL open fill, LOSS = -1R,
unresolved/EXCLUDED = 0R. Per-candle order mirrors the backtester:
resolve any OPEN position (open fills run BEFORE the same bar's
invalidation, unlike a resting limit), then the structural invalidation,
then signals. STEP 2 -- CONFIRMATION DIAGNOSIS (Phase 4H step 8):
MARKET_CONFIRMATION's 0 fills are ATTRIBUTED, not dismissed, with
rejection-stage counters candidates / rejected_structure / rejected_trend
/ rejected_distance / rejected_volume / rejected_orderflow / triggered,
the reason decided at settle with priority structure > trend > distance,
the partition invariant rejected_structure + rejected_trend +
rejected_distance + triggered == candidates (volume/orderflow are kept at
0 -- that axis does not exist -- so the diagnosis is provably complete),
and the primitive diagnosed on every bar independent of the breakout
(co-existence, exactly like STATUS 104). STEP 3 -- WIRING:
causal_validation on PipelineContext (_new_causal_validator factory +
field + reset()); TradeSetupBuilder validation.observe() beside the
shadow's (same trade-eligible, first-appearance-per-structural_id
population); Backtester causal_validation.advance() every candle beside
entry_shadow.advance; tests/test_backtester prints PHASE 4H CAUSAL
BREAKOUT VALIDATION ALL/BULLISH/BEARISH gated on ENABLE_CAUSAL_VALIDATION
with setups_discovered from the ledger's distinct_structural_ids.
STEP 4 -- CONFIG (config/risk_settings.py, Phase 4H block):
ENABLE_CAUSAL_VALIDATION = True; INTRABAR_POLICY = "CONSERVATIVE"; reuses
ENTRY_TRACKING_WINDOW_BARS=60. STEP 5 -- TEST PROOF: NEW
tests/test_causal_validation.py (32 stdlib-only tests): freeze under
setup/feasibility mutation, bullish/bearish triggers against the exact
trigger contract, stop-breach-BEFORE-trigger, trigger-bar-never-enters,
entry price == OPEN of trigger+1, entry executes even when the entry bar
gaps against (market order), last-in-window trigger non-executable +
triggers-without-executable-next-bar count, CONSERVATIVE/OPTIMISTIC/
EXCLUDE intrabar resolution incl. an SL+TP-spanning candle, EXCLUDE drops
the trade from W/L, clean win/loss unambiguous, MAE/MFE include the entry
bar's post-open wicks beyond the cap levels, R-multiple math (WIN =
reward/risk from open fill, LOSS = -1, UNRESOLVED = 0), the full
report-math table (win rate / PF / gross P/L / expectancy / avg R / max
drawdown R+pct / avg bars to entry / avg MAE-MFE ATR) under all three
policies, the confirmation partition invariant,
confirmation-independent-of-breakout, dedup + trade-ineligible skip +
order-context attach, ENABLE_CAUSAL_VALIDATION gating leaves no traces,
and post-decision candle mutation + post-observe setup mutation changing
NOTHING (no look-ahead). Full suite 483/483 green (451 + 32), compileall
clean. STEP 6 -- 5000-BAR REGRESSION (same live BTCUSDT 1m; funnel
identical to STATUS 104: 98 structural / 68 dupes / 18 ideas / 0 clusters
/ 19 orders (1F/16E/2I) / 11 cooldown suppressions / avg pending 0.1 max
3 -- NOTE: the cosmetic "First reached at bar" sub-line printed 1776 this
run vs 1820 in the STATUS 104 evidence and 1799 in the Phase 4G review
paste, with otherwise identical funnel numbers -- a cosmetic ledger-line
drift, not an executable-behavior change; 304 trade-eligible). The causal
walk REPRODUCES the STATUS 104 breakout counts exactly (292 triggers -> 292
fills, 238W/38L/16U) and records ZERO ambiguous candles/trades in the whole
run, so all three intrabar policies render identical; MAE/MFE are NOT
comparable to the shadow's close-entry excursions (open-fill convention +
entry-bar inclusion + stop/target flooring).

PHASE 4H CAUSAL BREAKOUT VALIDATION (ALL, 98 discovered / 304 eligible;
window 60 / NEXT_BAR_OPEN execution)

  Policy      Trigs Fills Ambig  W   L  Unr Exc  Win%  PF   ExpR  MaxDD%  MAE  MFE  (ATR)
  CONSERVATIVE 292   292   0   238  38  16   0  86.2  2.58  0.22   25.7  21.28 11.29
  (OPTIMISTIC / EXCLUDE identical: zero ambiguous intrabar candles this run)

  PRIMARY CONSERVATIVE: Expectancy / avg R +0.217 R; gross P/L 97.98R /
  38R; max drawdown 15.39R (25.7% of the R-curve peak); triggers without
  executable next bar 0; avg bars creation -> entry 2.0.

  BULLISH (141): CONSERVATIVE 138 fills 110W/15L/13U 88.0% PF 2.47 ExpR
  +0.18 MaxDD% 39.4, MAE/MFE 24.28/9.92 ATR. BEARISH (163): 154 fills
  128W/23L/3U 84.8% PF 2.65 ExpR +0.25 MaxDD% 25.4, MAE/MFE 18.60/12.51 ATR.

  MARKET_CONFIRMATION DIAGNOSTICS (step 8) -- ALL: candidates 304;
  rejected_structure 91; rejected_trend 0; rejected_distance 213;
  rejected_volume 0; rejected_orderflow 0; triggered 0
  (91 + 0 + 213 + 0 == 304). BULLISH (141): 36 / 0 / 105 / 0 / 0 / 0.
  BEARISH (163): 55 / 0 / 108 / 0 / 0 / 0.

VERDICT: the breakout win rate SURVIVES strict causal execution --
292/304 eligible setups trigger one bar out and fill at the next bar's
open; under the CONSERVATIVE (stop-first) primary policy the shadow's
238W/38L/16U holds EXACTLY (86.2% win rate, PF 2.58, +0.217R per trade,
25.7% max drawdown on the R curve) with ZERO ambiguous intrabar candles to
dispute. Breakout continuation is NOT an artifact of retrospective entry:
the next-bar OPEN fill reproduces the STATUS 104 result because 1m BTC
continues ~11 ATR post-trigger on average against ~1-2 ATR risk -- but the
21 ATR average MAE (>> the 1R stop) is a loud warning that continuation
trades are held through deep post-trigger countermoves, so the 86% win
rate papers over large per-trade drawdowns (bullish MaxDD 39.4% demands
the most respect). The MARKET_CONFIRMATION 0-fill mystery is now
STRUCTURALLY explained: of 304 eligible setups, 213 never reached E within
60 bars (the Phase 4G distance finding) and 91 were invalidated by a
structural stop breach before confirmation could matter; ZERO were
trend-rejected (reached E but failed to close beyond) and ZERO confirmed
-- a close-beyond confirmation cannot fire where price virtually never
retraces to E at all. The entry-distance-vs-expiry finding stands
unchanged (RECORDED, NOT TUNED, per the user): the 0-2 ATR fill population
vs the 16+ ATR unfilled remains the binding constraint; the 30 ATR
eligibility threshold is UNTOUCHED. CAVEATS (mandatory honesty): 238 wins
over one 5000-bar window is a stronger but still single-window,
no-slippage/no-fee/no-budget in-sample sample; EXCLUDE only renders
identically because no ambiguous intrabar candle occurred -- it remains a
distinct policy elsewhere; the 21 ATR average MAE uses the deliberately
pessimistic open-fill/entry-bar-inclusive/floor-at-stop convention.
DECISION DEFERRED: BREAKOUT_CONTINUATION must NOT become executable and no
threshold may move until the user reviews this report.
106. PHASE 5A / 5B -- EXECUTABLE BREAKOUT CONTINUATION (user-review
approved: the Phase 4H BREAKOUT validation was ACCEPTED and moved from
shadow to executable). Entry models became first-class canonical
values (core/execution/entry_model.py): a SetupCandidate is routed by
the EntryModel Router and the LIMIT / NEXT_BAR_OPEN execution channel
is carried OrderIntent -> Trade. The backtester gained the Phase 5B
branch: a NEXT_BAR_OPEN order is decided by the canonical
BreakoutContinuationEntryModel under the Phase 4H causal rules
(trigger at close, fill at the OPEN of trigger+1, gap-against still
executes, market fill) and sized by _resize_for_actual_entry, with the
same single-position, active-mode and portfolio gates applied to the
market fill. tests/test_backtester_breakout.py (8 tests) proves the
executed ledger: 112.0 entry on trigger+1 bar, NEXT_BAR_OPEN, closed
ledger + account exactly consistent.

107. PHASE 5C -- CANONICAL ENTRY-MODE ROUTING (+8 tests). The previous
router SILENTLY degraded unknown/AUTO config to LIMIT_RETEST, so a
research-BREAKOUT / production-LIMIT mismatch was possible. Now
select_entry_mode() honors the setup's carried entry_mode else the
configured mode; AUTO and undeclared modes RAISE EntryModeRouterError
(never a fallback for production execution); active_entry_modes()
collapses ONLY empty config to the LIMIT_RETEST baseline. A mode-less
legacy order in the backtester is anchored to the LIMIT_RETEST channel
-- it is never re-routed to whatever ENTRY_MODE is configured (no
invisible strategy substitution). MARKET_CONFIRMATION gains the
canonical trigger gate (reached AND close-beyond-E) so an active
MARKET_CONFIRMATION run can never silently execute as LIMIT_RETEST.

108. PHASE 5D -- ISOLATED EXECUTION COMPARISON + PRODUCTION DEFAULT
(+6 tests). New core/validation/execution_comparison.py: each entry
mode runs as an INDEPENDENT pipeline + simulator + backtester over the
same bars / risk / capital / fee / slippage config, producing its own
orders / fills / trades / PnL / drawdown / performance columns
(win rate, PF, expectancy, avg R, fees, slippage, final equity) --
research shadows are never blended into a live ledger. PHASE 5C/5D
call: the engineering favored BREAKOUT (Phase 4H causal: ~86% win
rate, PF 2.24, +0.182R; LIMIT ~0% fill in the SAME context), so the
PRODUCTION DEFAULT was deliberately flipped: ENTRY_MODE =
BREAKOUT_CONTINUATION, ACTIVE_ENTRY_MODES = ("BREAKOUT_CONTINUATION",)
(config/risk_settings.py). The 5000-bar regression now EXECUTES
BREAKOUT: 30 orders, 16 filled, 11 expired, 3 invalidated, 16 trades
(was LIMIT 21 / 1 filled) -- the main backtester now exercises the
strategy that was researched. EXECUTED LEDGER (recorded): 16 closed
trades, 13 WIN / 3 LOSS, win rate ~81.3%, net PnL +0.34 (zero-cost
diagnostic). Direction split: BULLISH 6 trades (3W/3L, net -0.60) vs
BEARISH 10 trades (10W/0L, net +0.94) -- the bullish-vs-bearish
asymmetry (bearish carrying the edge) SURVIVES into real execution
and is on the Phase 7 research agenda before any multi-crypto live
trading. LIMIT_RETEST stays a mode-less baseline
channel + selectable comparison mode (no thinning). Tests build the
explicit entry-mode (default LIMIT) for construction contracts; the
existing 24+8+8+6 entry-model/router/breakout/comparison suites stay
green. Full suite 522/522 OK, compileall clean.
109. PHASE 6A -- DYNAMIC DELTA PRODUCT DISCOVERY (+27 tests). The
engine now catalogs EVERY Delta product from /v2/products -- spot,
perpetual, future, options and unknown contract types -- through an
INJECTABLE transport (ProductClient.fetch/fetch_cached, default
DeltaREST; tests swap a FakeTransport, zero network), normalizes each
raw payload into the canonical exchange-agnostic Instrument
(data/delta/product_normalizer.py: lowercase contract_type via
product_type_from_delta, asset-dict underlyings, safe numeric
coercion, trading_enabled derived from is_delisted/is_disabled/
is_unlisted/state; reuse every delta_mapper real-payload defense) and
tracks lifecycle in a persistent JSON registry
(core/registry/instrument_registry.py). Lifecycle: FIRST sighting ->
NEWLY_LISTED candidate; repeat with changed economics re-validates;
a DELISTED product that reappears is a re-listed candidate; unchanged
NEWLY_LISTED -> ACTIVE once sighted again (mark_present confirms
prior-pass sightings and DELISTs what vanished -- gracefully, never
deleted); mark_eligible/mark_ineligible + executable() gate state.
Repeat upserts PRESERVE lifecycle state (an ELIGIBLE instrument is
never silently reset). core/registry/eligibility.py =
InstrumentEligibility gates 1-4 (identity / trading_enabled / canonical
strategy product type / precision) with the liquidity gate a
DENY-BY-DEFAULT when quote_volume_24h is None -- never trade what we
cannot measure; options/unknowns are DISCOVERED but never eligible
until a supporting layer exists. refresh_instrument_registry() runs
discover -> upsert -> mark_present -> save and detects a NEW listing
on the NEXT pass with zero restart. NEW tests: tests/
test_instrument_discovery.py (26) + relist path (1) -- client cache
TTL, normalizer fidelity per type, first-seen/confirmed/delisted/
re-listed lifecycle, persistence round-trip via temp JSON, refresh
new-listing + delisting + no-duplicate passes, eligibility gates.
No hardcoded symbol anywhere -- the registry is single source of
truth; phases 6B (market universe / liquidity + history gates) and
6C (multi-symbol scanning) build on this. Full suite now 549/549 OK,
compileall clean. Commit: independent Phase 6A milestone.

110. PHASE 6B -- MARKET UNIVERSE + ELIGIBILITY ENGINE (+20 tests). New
core/universe/ package builds the ELIGIBLE trading universe on top of
the Phase 6A registry. (a) universe_policy.py -- UniversePolicy
(min_quote_volume_24h, min_history_bars; None disables the bound but
NOT the data requirement). (b) eligibility.py extended: history gate
(NO_HISTORY_DATA / INSUFFICIENT_HISTORY) added to the liquidity gate
(NO_LIQUIDITY_DATA / LOW_LIQUIDITY); the valid() envelope (identity +
trading_enabled); NOT_CONFIRMED for first-sighting candidates. (c)
universe_manager.py -- UniverseManager cascades the gates over every
confirmed registry instrument with INJECTABLE liquidity + history
providers (duck-typed, mockable): NEWLY_LISTED single sightings are
NEVER eligible the same pass; DELISTED can never re-enter the
universe; every re-check WRITES ELIGIBLE / INELIGIBLE + reason back
to the registry (mark_eligible now clears the stored reason); no
provider/no data degrades to an EMPTY universe, never a silent
everything-goes catalog; executable_symbols() is the Phase 6C
scanning input; refresh() = discovery heartbeat + eligibility
cascade. Fixed a silent footgun: UniverseManager used

egistry or InstrumentRegistry(), but an empty InstrumentRegistry
is FALSY (it defines __len__) so the passed registry was DROPPED --
now is not None. (d) market_universe.py -- immutable MarketUniverse
snapshot (symbols / get_by_symbol / contains / reasons / captured_at).
(e) refresh_scheduler.py -- RefreshScheduler drives discovery +
eligibility on a cadence with an injectable clock (due /
run_if_due / force_refresh; interval <= 0 = always due); a failed
discovery pass is RECORDED and the loop continues (last_universe /
last_summary / errors). NEW tests: test_market_universe.py (13:
eligible cut, executable feeding, NOT_CONFIRMED same-pass rule,
LOW_LIQUIDITY + reason persisted, NO_LIQUIDITY_DATA, INSUFFICIENT/
NO_HISTORY, empty-universe degradation, flip both ways, options never
eligible, snapshot semantics), test_new_listing_refresh.py (7: full
graduation BTC/ETH then SOL over passes 1-4, delisted never revives
via provider data, no catalog duplication over 5 passes,
eligibility-only refresh, scheduler interval / zero-interval /
force-refresh / failure isolation -- ALL offline via FakeTransport +
fake clock; the scheduler tests injected the transport so no pass
touches the live API). Full suite 569/569 OK, compileall clean.
Commit: independent Phase 6B milestone.

111. PHASE 6C -- CANONICAL IDENTITY + MULTI-SYMBOL SCANNING (+25
tests). New core/identity/ package builds the canonical setup identity
ONCE at setup creation -- {exchange}:{instrument_id}:{timeframe}:
{direction}:{strategy}:{setup_id} (e.g. delta:27:1m:BULLISH:
BREAKOUT_CONTINUATION:OB-990) -- and it flows UNCHANGED through
SetupCandidate -> OrderIntent -> Trade (the builder stamps it, RiskEngine
and TradeSimulator copy it VERBATIM, never reconstructed downstream).
instrument_identity.py: build_setup_identity with validation (non-empty
segments + BULLISH/BEARISH, IdentityError on malformed) and a round-trip
splitter. New core/scanning/ package orchestrates ONE isolated pipeline
per instrument: symbol_pipeline.py (fresh PipelineContext / MarketState
with exchange+instrument_id, world, EventBus, TradeSimulator, Backtester
per scan -- ZERO shared mutable state between instruments; injectable
world factory defaulting to InstitutionalPipeline; data_source contract
get_candles(symbol, timeframe, limit); accumulates every candle's setups
into the result), multi_symbol_scanner.py (consumes ONLY the universe
eligible cut -- MarketUniverse.eligible_instruments() / registry
executable() / iterable -- never hardcoded symbols; deterministic
(exchange, instrument_id, symbol) ordering independent of insertion
order; per-symbol FAILED/SKIPPED/SUCCESS isolation with errors
captured and neighbours untouched; empty universe degrades to a clean
empty result), scan_result.py (ScanStatus + SymbolScanResult with
setups/decisions/orders/trades + MultiSymbolScanResult aggregation).
MarketState gained exchange + instrument_id (defaults ""); legacy
single-symbol harnesses stay byte-identical (canonical_id ""). NEW
tests: test_scanning.py (25: identity format/divergence/validation/
round-trip suffix preservation, setup->order->trade canonical flow
end-to-end, per-instrument namespacing, legacy empty-id backward
compat, eligible-cut routing via MarketUniverse AND registry,
empty-universe degradation, no-hardcoded-symbol source regression,
per-symbol world isolation + cross-symbol mutation immunity,
failure isolation (A ok / B raises / C ok), NO_DATA skip, ordering
determinism under reversed universes + repeatability). All offline:
scripted four-engine world + per-symbol data sources, ENTRY_MODE
pinned to LIMIT_RETEST. Full suite 594/594 OK, compileall clean.
Commit: independent Phase 6C milestone.
112. PHASE 6D -- REAL-TIME MULTI-SYMBOL SUBSCRIPTIONS (+32 tests). Data layer delivers live market data independently to every eligible instrument without touching strategy, execution, or portfolio logic. New data/realtime/ package: subscription_state.py (explicit lifecycle states STOPPED/CONNECTING/LIVE/RECONNECTING/STALE/FAILED -- no implicit is_connected booleans -- plus per-subscription counters received/delivered/duplicates/out_of_order/forming_skipped/reconnect_attempts and an assert_valid_transition matrix), reconnect_policy.py (exponential backoff base_delay x factor^(attempt-1) capped at max_delay, deterministic, opt-in jitter, optional max_attempts budget -> ReconnectExhausted), candle_router.py (per-symbol integrity gate: a CLOSED candle is delivered AT MOST once and in chronological order; FORMING candles (closed=False) never reach strategy logic -- BREAKOUT triggers stay causally aligned to NEXT_BAR_OPEN; bounded seen-timestamp memory survives a reconnect so replayed candles are duplicate-dropped and older candles are out-of-order-dropped), stream_health.py (staleness detection, injectable clock), stream_worker.py (SubscriptionWorker: one logical subscription driven by the state machine; event-driven, NON-BLOCKING -- retries scheduled as clock deadlines and fired by poll(), so one failing stream can NEVER stall another; forming ticks keep the subscription fresh; closed candles pass the router), subscription_manager.py (MultiSymbolSubscriptionManager consumes MarketUniverse.eligible_instruments() / any iterable -- never hardcoded symbols; sync() diffs future - current -> ADD/REMOVE/KEEP in place with NO restart; FAILED workers re-added on the next universe pass; ONE SHARED multiplexed transport kept across passes; poll() isolates per-worker failures incl. ReconnectExhausted; stop_all() releases the connection, a later sync rebuilds it). Candle gained closed (FORMING/CLOSED provenance) and symbol delivery-scoping fields -- both defaulted so the backtest candle shape is byte-identical. New data/delta/delta_subscription_stream.py production transport follows Delta's ACTUAL websocket model: ONE connection, ONE channels payload listing every desired symbol, per-symbol CandleBuilder rolls closed candles on bucket boundaries with throttled forming heartbeats, on_down() fanned to every route; websockets sync client imported lazily (offline tests use FakeTransport). NEW tests: tests/test_realtime.py (32: candle provenance defaults, router integrity -- closed-once / duplicate / out-of-order / forming-never-forwarded / reconnect-boundary / chronological, explicit state set + illegal-transition raises, worker lifecycle -- start LIVE / disconnect->RECONNECTING / reconnect restores with no duplicate subscription / forming-not-delivered / closed-delivered-once / wrong-symbol dropped / STALE then LIVE / budget-exhausted->FAILED / start-raise->RECONNECTING / stop unsubscribes, manager -- eligible-subscribed / MarketUniverse duck accepted / dynamic add with the SAME shared transport / BTC+ETH->BTC+SOL diff (BTC worker object retained, ETH unsubscribed, SOL added) / ineligible+delisted removed / idempotent re-sync / A-and-C-continue-while-B-reconnects / one-stream-failing-ignored / exhausted-stream-fails-alone / failed-worker-healed-next-pass / stop-all closes transport / transport rebuilt after stop_all). All offline (FakeTransport + FakeClock). Full suite 626/626 OK, compileall clean. Commit: independent Phase 6D milestone -- Phase 7 BREAKOUT directional research stays separate.

113. PHASE 6E -- REAL-TIME CLOSED-CANDLE INTEGRATION, PAPER MODE (+6 tests). Wires the 6B universe refresh and the 6D real-time closed-candle delivery into the frozen 6C SymbolPipeline, running continuously as PAPER trading (zero exchange writes). New core/runtime/ package, four orchestrator modules that COMBINE existing blocks and add NO strategy / execution / portfolio logic: execution_port.py (the ONE paper/live execution seam -- ExecutionPort protocol execute/fetch/cancel/balance/positions, PaperExecutionAdapter audits the would-be intent + returns the paper envelope and raises PaperOnlyError on every live-only op, future LiveDeltaExecutionAdapter is the only other implementation), pipeline_registry.py (stable per-instrument pipeline ownership keyed by (exchange, instrument_id) via instrument_identity_key; reconcile() diffs the eligible cut -> ADD / RETAIN / RETIRE with retired pipelines kept in a readable snapshot; instruments built through the injectable world_factory and reset exactly once at ADD, so a retained instrument NEVER rebuilds its window across refreshes), paper_runtime.py (PaperRuntime: per-instrument continuous unit owning ONE frozen SymbolPipeline driven through the canonical core/live/BrokerEngine with dry_run=True -- the SAME explicit per-candle flow as the Backtester: world on_candle -> RiskEngine OrderIntent -> TradeSimulator paper fill -> SL/TP exits -> TradeRegistry = the PAPER_TRADE_REGISTRY; PaperExecutionAdapter injection is the ONLY live difference; canonical_id flows setup -> order -> trade verbatim), realtime_engine.py (RealTimeEngine: RefreshScheduler pulse -> registry.reconcile + manager.sync -> manager.poll() -> _on_closed_candle resolves symbol -> eligible instrument record -> identity key -> that runtime only; identity-key routing means a BTC candle can never mutate the ETH pipeline, never by subscription or position order; statuses() merges runtime + 6D subscription state, ledger()/all_trades() expose the paper book). NEW tests: tests/test_runtime_integration.py (6: eligible-to-subscription-to-pipeline flow incl. forming-never-delivered + unknown-symbol unrouted + statuses merge; dynamic BTC+ETH -> BTC+SOL pass asserting the BTC PaperRuntime OBJECT is retained, ETH retired to the snapshot + unsubscribed + its candle goes nowhere, SOL created fresh -- never a rebuild on refresh; candle routing isolation -- BTC candle touches only the BTC pipeline and vice versa with per-symbol market state preserved; duplicate protection end-to-end -- same-pass replay deduped AND post-reconnect replay deduped (subscribe_calls==2, routed exactly once), new closed candle delivered once, forming replay never reaches the pipeline; deterministic paper execution -- known BULLISH setup -> paper FILLED at order entry -> TARGET hit -> CLOSED WIN with canonical_id / setup_id / entry_mode preserved, pnl=10.0 net zero costs, account 2010, order FILLED + trade attached, then the defensive STOP-LOSS variant booking LOSS at -10 / balance 1990, plus the PaperOnlyError guarantee on balance/positions/cancel). All offline via the scripted world (BrokerEngine's pipeline-compatible object contract) + FakeTransport + FakeClock + SnapshotManager. Full suite 632/632 OK, compileall clean. Commit: independent Phase 6E milestone -- the real-time paper integration is complete; Phase 7 BREAKOUT directional robustness research stays the separate next milestone.

114. PHASE 7 -- BREAKOUT DIRECTIONAL ASYMMETRY RESEARCH (research-only,
18 tests). Establishes WHY the same BREAKOUT_CONTINUATION architecture
behaves differently per direction (reported: bearish PF 3.05 / +0.2769R /
MAE-DD 23.6%; bullish PF 0.92 / -0.0185R / MAE-DD 321.5%) -- a RESEARCH
harness that is DELIBERATELY SEVERED from production. New core/research/
namespace + core/research/breakout_asymmetry/ package: features.py
(16-axis FeatureExtractor -> FeatureRow: direction, entry context,
risk geometry (risk ATR, entry distance ATR, stop ATR distance), zone
age, score, MFE/MAE ATR windows, trigger rate, reward:risk, fill-path),
outcomes.py (OutcomeClassifier + OutcomeProfile; buckets STOP_HIT /
TARGET_HIT / UNRESOLVED / EXCLUDED / NEVER_ENTERED; conservative
WIN/LOSS; MFE/MAE/payoff/PF/expectancy/win-rate/MAE-DD), origins.py
(OriginDecomposition + decompose_origins mapping measured asym to
origin A market / B structure-generation / C setup-selection / D
breakout-trigger / E stop-target geometry (MFE + MAE + RR three
metrics) / F execution / G data-sample imbalance, each with
present + asymmetry), counterfactual.py (CounterfactualStudy mirror
study -- 7D verdict EXECUTION-HELD-CONSTANT by construction, since
both directions already share identical causal execution), report.py
(AsymmetryReport with verify()/hypothesis()/summary()/dump();
load_dataset consuming a list of CausalValidationState / dicts / a
JSON path). Consumes ONLY the frozen CausalValidationState records
(core/setup/causal_validation.py); emits ONLY evidence -- nothing in
the research package is imported by any engine, no strategy change.
demo.py builds a synthetic mirror dataset reproducing the reported
shape and dumps results/phase7_report.json. NEW tests:
tests/test_breakout_asymmetry.py (18: dataset load + merge, outcome
bucketing + conservative win/loss, PF/expectancy/win-rate/MFE/MAE/
payoff/MAE-DD math, origin decomposition truth (E geometry dominates),
counterfactual held-constant, full report assembly + verify()/
summary()/dump() round-trip, fidelity that the described bullish-vs-
bearish asymmetry shape decomposes to the correct origin). All offline,
stdlib-only, synthetic causal data. Full suite 650/650 OK, compileall
clean. Commit: independent Phase 7 research milestone -- the evidence
points to setup/geometry (origin E) as the dominant cause, NOT
execution (F held constant); a directional BREAKOUT_CONTINUATION
BULLISH/BEARISH policy (7E) is NOT introduced in this phase -- it
remains gated behind out-of-sample validation on real (non-synthetic)
causal data.

115. PHASE 7E -- REAL-DATA OUT-OF-SAMPLE CAUSAL VALIDATION (research-only,
+8 tests). Runs the FROZEN production causal pipeline against UNSEEN real
BTCUSDT 1m history and renders the A/B/C gate (GO / NO-GO / INCONCLUSIVE)
on the directional hypothesis (bearish-strong / bullish-weak, the shape
the synthetic mirror / user baseline reported). NEW
core/research/breakout_asymmetry/realdata.py: fetch_and_cache_oos_candles
(fetches ~10,000 real 1m bars live from Delta via HistoricalLoader,
caches the pinned OOS sample to the git-ignored data/history/
BTCUSDT_1m_oos.json for reproducible offline re-runs, returns
chronological Candle objects), run_oos_causal_pipeline (replays the real
candles through the IDENTICAL frozen construction -- PipelineContext +
InstitutionalPipeline + EventBus + TradeSimulator + Backtester.run() with
ENTRY_MODE pinned to BREAKOUT_CONTINUATION, then restores
ENTRY_MODE/ACTIVE_ENTRY_MODES verbatim), _verdict (the 7E.9 gate: it
tests the SIGN of the directional profit signal -- win-rate AND
expectancy -- NOT a bare geometric |asymmetry|, so a real result whose
gap is absent or REVERSED reads NO-GO/outcome B instead of a spurious
GO), run_7e + main (builds the AsymmetryReport over the real states and
dumps results/phase7e_real_oos_report.json with verdict + provenance
metadata). report.py::verify() fixed to reconcile the FULL classified
population (origins.total_triggered == outcomes == bucketed == 692) and
surface never_entered (18) as a diagnostic (triggers-without-entry are
part of the population per causal Rule 2 vs Rule 3). REAL RESULT on
10,000 bars / 692 settled states (268 BULLISH / 424 BEARISH): BOTH
directions profitable; bullish is slightly STRONGER (win 79.2% vs 74.5%,
PF 1.32 vs 1.23, expectancy +0.067R vs +0.059R); the bearish-strong /
bullish-weak hypothesis is REJECTED (win-rate gap -4.7pp below the 5.0pp
floor, reversed sign) -> 7E VERDICT NO-GO (outcome B); the 7E gate is NOT
crossed -- NO directional BREAKOUT_CONTINUATION BULLISH/BEARISH branch.
NEW tests: tests/test_breakout_asymmetry_7e.py (8: directional gate GO
when hypothesis reproduces / NO-GO when REVERSED (bullish stronger) /
NO-GO when near-symmetric / INCONCLUSIVE when one direction absent or
sample too thin, OOS cache round-trip + chronological order,
run_oos_causal_pipeline config restoration). Offline EXCEPT the real-data
run, which uses the cached sample. Full suite 658/658 OK, compileall
clean. Commit: independent Phase 7E milestone; baseline d3eb2c8 immutable;
the real OOS evidence REJECTS the synthetic directional hypothesis, so no
directional policy is introduced and no production code is modified.
116. PHASE 8 -- PORTFOLIO RISK & CAPITAL COORDINATION, FIRST-CLASS CORE
LAYER (+17 tests). Turns the portfolio risk gate from a backtest-only
adapter into a first-class core/risk/portfolio.py::PortfolioRiskManager
that now governs BOTH the backtest path (PortfolioBacktester) AND the
live/paper path (RealTimeEngine/PaperRuntime/BrokerEngine), so a single,
shared portfolio policy coordinates capital across every symbol in both
 regimes. CARDINAL INVARIANT carried forward verbatim: the portfolio layer
GATES (accept/decline) an otherwise-valid trade but NEVER mutates the
setup's entry/stop/target/direction/strategy logic -- flow stays
SymbolPipeline -> Strategy decision -> RiskEngine -> OrderIntent ->
Portfolio Risk Gate -> Execution. (1) NEW core module core/risk/portfolio.py:
order-aware gate order_allows(order) is a PURE DECISION (inspects order +
current portfolio state, returns bool, sets last_reason on a False verdict,
NEVER touches the order/ledger); register_open(order) / release_closed(trade)
are BOOKKEEPING (ledger, realized PnL, peak-equity, daily-loss); optional
DISABLED-BY-DEFAULT caps -- max_positions (concurrency), max_portfolio_risk
(ABSOLUTE aggregate-R budget, matching the legacy manager -- independent of
equity), max_total_exposure_pct / max_directional_risk_pct /
max_correlated_risk_pct / max_daily_loss_pct (equity-scaled %), max_per_symbol_notional
(absolute currency), equity basis, correlation_groups (symbol->group map);
properties current_risk/current_notional/open_positions/direction_risk/
correlated_risk/equity/realized_pnl/peak_equity/drawdown/drawdown_percent;
snapshot(); reset(); _dims() normalizes an OrderIntent/Trade-like object OR
primitives. It ALSO implements the legacy duck-typed surface (can_open /
register_trade / close_trade / current_risk / open_positions /
open_by_symbol / equity / reset) as a drop-in SUPERSET of the legacy
risk/portfolio_risk.py, so PortfolioBacktester's adapter works verbatim with
NO change. (2) LIVE/PAPER WIRING: BrokerEngine.__init__ gained optional
portfolio_gate(order)/portfolio_release(closed_trade) hooks mirroring the
Backtester contract -- the gate is consulted in _route() right after the
OrderIntent resolves and BEFORE open_trade/execute; a False verdict returns
WITHOUT routing (order/ledger untouched, logged PORTFOLIO_GATE_DECLINED);
portfolio_release is called after a close in BOTH _book_closed (paper) AND
_book_live_close (live). PaperRuntime and RealTimeEngine thread a SHARED
PortfolioRiskManager through __init__ (RealTimeEngine defaults to a
default-NEUTRAL manager so live/paper behavior is unchanged unless caps are
supplied); every PaperRuntime's BrokerEngine gets the same _portfolio_gate /
_portfolio_release closures. Default neutrality holds: with no caps the gate
always allows and nothing changes for a default run. (3) TESTS: NEW
tests/test_portfolio_risk_core.py (17): default neutrality (no caps allow
all); order_allows is a pure decision (repeated calls never mutate order or
ledger); last_reason set on decline; each dimensional cap (concurrency,
aggregate-R budget, total notional exposure, per-symbol notional,
directional, correlated via correlation_groups, daily-loss guard); release
frees the slot + folds PnL into equity + frees direction/correlation
ledgers; reset determinism; legacy primitive surface (can_open/
register_trade/close_trade) drives PortfolioBacktester end-to-end with the
core manager; and a live/paper BrokerEngine integration proving a SHARED
max_positions gate declines the second symbol's otherwise-valid order while
holding the first, then accepts it after release. Proof: compileall clean;
full suite 675/675 OK (658 + 17 new; zero existing-test changes). Docs:
import_manifest.md added the PORTFOLIO RISK & CAPITAL COORDINATION section
(STATUS 116, AST source census: realtime_engine imports core.risk.portfolio);
project_manifest.md marks PortfolioRiskManager (core) Active. Commit:
independent Phase 8 milestone -- portfolio risk and capital coordination are
now a first-class core layer shared by backtest, paper and live; Phase 7E's
NO-GO stands (no directional policy was introduced).
117. PHASE 8B -- SHARED PORTFOLIO CAPITAL & DETERMINISTIC ALLOCATION, CORE
LAYER (+20 tests). Infra phase (NOT strategy optimization): turns the
Phase 8 gate into a reservation-based capital-lifecycle foundation by
adding three dedicated core modules. NEW core/risk/capital.py:
SharedCapital -- reservation-based equity envelope (equity = basis +
realized PnL; reserved_capital = sum of live reservations; available_capital
= deployment_cap - reserved). can_reserve(amount) is a PURE DECISION
(consults available, sets last_reason='insufficient_capital', never mutates);
reserve(rid, amount) / release(rid, pnl) / cancel(rid) are BOOKKEEPING
(cancel returns capital with NO realized PnL -- the failed-execution-after-
reservation path). NEW core/risk/portfolio_state.py: CapitalCandidate (pure
data: symbol/direction/correlation_group/risk/capital; from_order() reads
OrderIntent fields) + PortfolioState -- the UNIFIED state owning the
SharedCapital envelope, the risk budget (max_portfolio_risk, absolute R),
equity-scaled total/directional/correlated % caps, absolute per-symbol
capital, correlation_groups, and the RESERVATION LEDGER (rid ->
{symbol,direction,group,risk,capital}). can_accept(candidate) is the PURE
decision gate (risk_budget / insufficient_capital / total_exposure /
per_symbol_capital / directional_limit / correlation_limit); reserve(candidate)
returns a rid, release(rid, pnl) / cancel(rid) manage the lifecycle. NEW
core/risk/allocator.py: CapitalAllocator + AllocationResult -- DELIBERATELY
DETERMINISTIC allocation (strict input order, NO ranking -- opportunity
selection belongs to a later 8C / Confluence layer). Reproduces the canonical
example exactly: equity $10,000 / max_portfolio_risk 2R -> BTC ACCEPT 0.8R /
ETH ACCEPT 0.7R / SOL REJECT-DEFER (0.8+0.7+0.9=2.4R > 2R, remaining 0.5R).
WIRING (default-neutral, parity by construction): PortfolioBacktester and
RealTimeEngine each gained an optional portfolio_state=None; when provided
the per-symbol gate/release run through the SHARED state's lifecycle
(can_accept + reserve on open; release on close, folding PnL into shared
equity), so backtest AND paper/live consume the SAME shared capital --
verified byte-identical (+10 PnL folds 10000 -> 10010 through both paths).
When None (default) behavior is UNCHANGED (no state; legacy gates).
RESERVATION ID mapping is symbol->rid (single-position-per-symbol) held on
the orchestrator and cleared on release / on run reset. Tests:
tests/test_portfolio_capital_8b.py (20): equity/available/reserved buckets;
reserve moves capital out of available; release returns + folds PnL;
insufficient-capital reason; cancel returns no-PnL; the canonical 2R example
(SOL deferred, remaining 0.5R); allocation determinism; first-come-first-
served no-ranking; simultaneous-candidates; THE CAPITAL LIFECYCLE (A reserve
-> B reserve -> A closes -> release -> C now allowed, equity 10010);
closed trade releases capital; rejected order consumes no capital;
failed-execution cancels; directional limit; correlation limit; per-symbol
limit; multiple symbols independent reservations; reset; PortfolioBacktester
state lifecycle; BrokerEngine state lifecycle parity (identical resulting
shared state as backtest). Proof: compileall clean; full suite 695/695 OK
(675 + 20 new; zero existing-test changes). Phase 7E NO-GO and Phase 8 gate
UNCHANGED -- this adds the shared-capital foundation ONLY. Docs:
import_manifest.md added the SHARED PORTFOLIO CAPITAL & ALLOCATION section
(STATUS 117); project_manifest.md marks SharedCapital/PortfolioState/
CapitalAllocator Active. Commit: independent Phase 8B milestone; the
Confluence Engine (Phase 9) will be built ON this foundation later -- NOT
Wyckoff/ML yet, and no BREAKOUT/rules/7E results were modified.

118. PHASE 9A -- RESEARCH JOURNAL + CAUSAL OPPORTUNITY LEDGER, FOUNDATION
(+19 tests; infra phase, NOT AI/ML/strategy optimization). Adds a durable,
deterministic research record of every market OPPORTUNITY LIFECYCLE
(setup -> eligibility -> order -> fill/expiry/invalidation -> trade ->
close) as a pure OBSERVER of the frozen engine (never alters a decision).
NEW core/research/journal/ sub-package, split by responsibility:
research_enums.py (Provenance BACKTEST/PAPER/LIVE, SetupLifecycle,
OrderLifecycle, Result, EntryReached, EventType -- exact string contracts);
research_event.py (deterministic immutable event, sequence+bar-derived
event_id, NO random UUIDs); setup_record.py (observed setup facts + ALL
verbatim rejection reasons, never a generic REJECTED); order_record.py
(observed order lifecycle + excursion facts: min/max_high_since_creation,
entry_distance_from_nearest_price, bars_pending, entry_reached);
trade_record.py (outcome + R = pnl/risk_amount; MAE/MFE consumed from the
authoritative CausalValidator where available, never fabricated);
opportunity_record.py (immutable unified view + resolved terminal outcome);
research_repository.py (append-safe stdlib storage, deterministic ordering
by (exchange, instrument_id)); research_journal.py (the per-bar
observer/reconciler -- reads settled PipelineContext + TradeRegistry at
the end of every bar; fail-safe, swallows + logs, never raises into
trading; symbol-scoped opportunity keys so empty canonical ids never
collide across instruments; bounded post-terminal path observer for
missed-continuation OBSERVED facts -- was the target reached? what were
the extremes? -- never a hypothetical fill); journal_query.py (read-only
filters: provenance/entry_mode/rejection-reason/terminal-outcome/symbol/
status/result); journal_summary.py (counts + breakdowns reusing the
authoritative WIN/LOSS/R/PnL language; no reimplemented performance math).
WIRING (optional, default-zero-behaviour-change): Backtester.run gains
journal=None (observes at the settled end of each bar, finalize() once);
PortfolioBacktester.run gains journal=None (shared across symbols);
PaperRuntime + RealTimeEngine gain journal=None (PAPER provenance,
fail-safe try/except); the LIVE interface is prepared ONLY via the same
journal.on_bar_observed attach point -- live trading is NOT enabled.
Identity: reuses canonical build_setup_identity (exchange:instrument:
timeframe:direction:strategy:setup_id) -- expressed but never rewritten.
PROVENANCE is explicit (BACKTEST/PAPER), never inferred from filenames.
Counterfactual/simulation (SimulatedTrade, CounterfactualOutcome,
StrategyExperiment) is SEPARATED and deferred to later phases -- NOT
represented. No ML/AI/Wyckoff, no lookahead, no OOS contamination; Phase
7E NO-GO and 6C/6D/6E/7/8/8B frozen layers untouched (only optional
journal params added). Tests: tests/test_research_journal_9a.py (19):
records/repository/query/summary units; R + WIN/LOSS + terminal order
labels; event determinism + enum roundtrip; the full win lifecycle
(DISCOVERED->ORDER_CREATED->FILLED->FILLED_CLOSED with WIN outcome +
canonical id preserved from the filled trade); expiry + missed
continuation; same-bar stop-breach invalidation; verbatim rejection
reasons; canonical identity preserved/no rewriting; multi-symbol one
journal keyed by identity; PAPER provenance stamped; journal changes
nothing in engine behaviour (identical trade/order counts); research
failure never stops trading (fail-safe); missing journal is a no-op.
Proof: compileall clean; full suite 714/714 OK (695 + 19 new; zero
existing-test changes -- every new hook defaults to None). Docs:
import_manifest.md added the RESEARCH JOURNAL & OPPORTUNITY LEDGER section
(STATUS 118); project_manifest.md marks the journal modules Active with an
explicit NO-AI/NO-ML note. Commit: independent Phase 9A milestone; the
foundation is infrastructure-only -- the Causal Opportunity Ledger is now
queryable, while simulated/counterfactual analysis (and any AI/ML) is
explicitly deferred, and no BREAKOUT/rules/7E results were modified.

119. PHASE 9B -- DETERMINISTIC PARAMETER EXPERIMENTATION +
COUNTERFACTUAL OPPORTUNITY REPLAY LAB (+17 tests; research/simulation
ONLY, NOT production optimization). Adds the deterministic research
machinery that answers "what would have happened under an explicitly
supplied RR / expiry / entry-offset / entry-model / stop / target
configuration?". NEW core/research/lab/ sub-package, split by
responsibility: provenance.py (COUNTERFACTUAL / SIMULATED provenance,
distinct from the 9A BACKTEST/PAPER/LIVE); experiment_config.py
(immutable frozen ExperimentConfig -- entry model + params, stop_mode,
target_mode, rr, expiry, changed_filters; never mutates production
defaults); simulated_trade.py (first-class SimulatedTrade, frozen,
provenance===COUNTERFACTUAL, NEVER enters TradeRegistry);
counterfactual.py (CounterfactualOutcome, one replay result, to_trade()
materialization); opportunity_replay.py (causal candle-by-candle replay
from the decision bar forward; stop-before-target exit ordering mirrors
TradeSimulator; decision-time ATR reused from core/indicators/atr, no
lookahead; MAE/MFE tracked from fill only); entry_models.py (experimental
LIMIT_RETEST / BREAKOUT_CONTINUATION / MARKET_CONFIRMATION semantics);
exit_models.py (EXISTING_STOP / ATR / CUSTOM stop + EXISTING_TARGET /
FIXED_RR / ATR / CUSTOM target geometry); evidence.py (immutable
EvidenceSnapshot -- real decision-time facts only, Wyckoff reserved and
NOT fabricated); metrics.py (deterministic PF / win-rate / expectancy /
R / drawdown over COUNTERFACTUAL trades only); experiment_result.py
(machine-readable ExperimentResult + human summary);
experiment_runner.py (batch replay, deterministic experiment_id =
sha1(config params + baseline id), NO random UUIDs; per-opportunity
fail-tolerance records a warning and never corrupts other runs);
parameter_grid.py (THIN Cartesian sweep -- itertools.product, caller
insertion order, expiry_bars->expiry alias, rr=[] -> zero, no overrides
-> one baseline, unknown keys raise KeyError, base_config never mutated,
fresh config per combination, no shared mutable state); recovery.py
(opportunity recovery classification). ISOLATION: the lab reads
OpportunityRecords + candles only; never writes the production
TradeRegistry, Journal, PortfolioState, risk or strategy config; 7E/7/
8/8B/6C-6E untouched. NO lookahead, NO optimization selection, NO ML/AI.
Tests: tests/test_parameter_grid.py (17): expiry_bars alias; canonical
rr without alias; unknown key KeyError; cartesian order (rr x
expiry_bars); no overrides -> one baseline; rr=[] -> zero; 2x3x2=12;
base_config unchanged after combos AND sweep; exact config retained in
every ExperimentResult; deterministic + unique experiment ids; repeat
sweep identical ordering; independent execution (no shared state);
per-opportunity failure isolation; SimulatedTrade is COUNTERFACTUAL.
Proof: compileall clean; full suite 731/731 OK (714 + 17 new; zero
existing-test changes -- new package is additive, no production edits).
Docs: import_manifest.md added the PARAMETER EXPERIMENTATION &
COUNTERFACTUAL REPLAY section (STATUS 119); project_manifest.md marks
the lab modules Active with an explicit NO-AI / NO-OPTIMIZER note.
Commit: independent Phase 9B milestone; ParameterGrid only reports what
happened under each explicit configuration -- automatic optimization is
deferred to a later research/AI layer, and no BREAKOUT/rules/7E results
were modified.

120. PHASE 9C -- COUNTERFACTUAL OPPORTUNITY SIMULATOR (+47 tests;
research-only, NOT production optimization). The deterministic
one-opportunity engine that answers "this trade was rejected/unfilled
under the baseline; what would have happened under THIS exact entry
model / RR / expiry / offset / stop / target"? NEW
core/research/counterfactual/ sub-package:
counterfactual_config.py (immutable CounterfactualConfig wrapping the
deterministic 9B ExperimentConfig; explicit unknown-param rejection,
unsupported entry model -> loud ValueError, outcome_bars horizon
validation, deterministic identity = 9B experiment_id_for over merged
params + outcome horizon + baseline -- NO UUIDs; setup_view() hands the
EXPERIMENTAL levels to the canonical deciders without mutating anything);
opportunity_categories.py (deterministic 9A-fact-only classification:
FILLED / REJECTED / MISSED_CONTINUATION / INVALIDATED /
ENTRY_NOT_REACHED / NON_EVALUABLE, derived ONLY from terminal_outcome +
verbatim rejection_reasons); opportunity_simulator.py (OpportunitySimulator:
STRICT contract -- explicit is-not-None source extraction (a present 0.0 is
NOT missing); direction validation; experimental geometry validation
(finite, risk>0, stop/target on the correct side) -> deterministic
NON_EVALUABLE, never RR=0; CANONICAL entry routing through the frozen
production deciders core/execution/entry_model.get_entry_model for
LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION -- no entry
semantics reimplemented (fixes the 9B lab reimplementation gap), a mode
with no canonical decider is NON_EVALUABLE + warning, never invented;
entry window expiry-bounded; BREAKOUT next-bar-open fill with
NO_EXECUTABLE_BAR (trigger on last bar) DISTINCT from ENTRY_NOT_REACHED;
outcome walk runs through the EXPLICIT CounterfactualConfig.outcome_bars
horizon (None == production TradeSimulator holding contract), including
the fill bar exactly as production's paper engine does
(open_trade then update on the SAME candle), stop-before-target ordering
mirrors TradeSimulator.update; R / PnL / MAE / MFE from ACTUAL fill
(risk = |fill - stop|, LOSS == -1R) matching the canonical _r_multiple
contract; bars_in_trade counts the fill bar like production bars_held;
source OpportunityRecord never mutated); simulated_trade.py +
counterfactual_outcome.py (REUSE the frozen 9B SimulatedTrade /
CounterfactualOutcome -- no duplication); counterfactual_runner.py
(CounterfactualRunner: run_config / run_configs / grid -- native 9B
ParameterGrid integration, every combination evaluated independently,
deterministic order, deterministic unique ids, never blended).
ISOLATION: reads OpportunityRecords + candles only; every successful
simulation is COUNTERFACTUAL and NEVER enters TradeRegistry / Account /
PortfolioState / SharedCapital / paper / live / production journal;
7E/7/8/8B/6C-6E untouched. NO lookahead, NO optimization selection,
NO ML/AI -- recovery is measured, never pushed to production.
Tests: tests/test_counterfactual_simulation.py (47): config contract
(unknown param / unsupported entry model / outcome_bars validation /
deterministic + distinct ids / outcome horizon in identity / config
preserved); strict source extraction (explicit zero present, missing
falls through); canonical routing (LIMIT rests, MARKET fills at close,
BREAKOUT next open, NO_EXECUTABLE_BAR vs ENTRY_NOT_REACHED, unsupported
mode defensive NON_EVALUABLE); no lookahead (future-candle sweep never
changes the entry decision; breakout fill never uses trigger-candle
future); outcome parity (same-candle collision STOP wins; WIN math
fill-based R; LOSS -1R; multi-bar MAE/MFE/bars_in_trade); horizons
(entry expiry bounds the window; no-expiry finds later trigger;
outcome_bars caps the walk vs default to end == TradeSimulator parity);
fail-safe gates (invalid direction / zero-risk / invalid stop-target
geometry / decision bar outside series / malformed record ->
NON_EVALUABLE); determinism / immutability (repeated simulation identical,
config independence no blending, source record unchanged after 1 and many);
ledger isolation (COUNTERFACTUAL provenance, TradeRegistry/Account/
PortfolioState/SharedCapital untouched after materializing trades);
runner + ParameterGrid (cartesian order, distinct deterministic ids,
repeat-run id stability, base config preserved, no sharing, per-config
results reflect their own RR); opportunity recovery (REJECTED
TOO_FAR_FROM_MARKET / INSUFFICIENT_RISK_WIDTH / STALE_ZONE -> WIN under
alternative config; unfilled LIMIT recovered by switching to BREAKOUT;
missed continuation recovered by extending expiry; classification
vocabulary). Proof: compileall clean; full suite 778/778 OK (731 + 47
new; zero existing-test changes -- new package is additive, no production
edits, tracked .pyc restored before commit). Docs: import_manifest.md
added the COUNTERFACTUAL OPPORTUNITY SIMULATOR section (STATUS 120);
project_manifest.md marks the counterfactual modules Active with an
explicit NO-AI / NO-OPTIMIZER note. Commit: independent Phase 9C
milestone; the simulator only reports what would have happened under an
explicitly specified alternative -- automatic optimization and any AI/ML
research layer are deferred to 9D/9E, and no BREAKOUT/rules/7E results
were modified.

121. PHASE 9D -- EXPERIMENT MATRIX + RESEARCH ANALYZER (+45 tests;
research-only, NOT production optimization). The ANALYZER (not an
optimizer): consumes the frozen OpportunityRecords (9A) and the
deterministic 9C CounterfactualOutcome collections and produces, for
every explicitly supplied alternative configuration, the evidence that
answers WHAT HAPPENED / WHAT COULD HAVE HAPPENED / WHY IT WAS MISSED /
WHICH CONFIG RECOVERED IT / how many trades-wins-losses that would add
and at what cost in R-PnL-MAE / whether it holds across directions /
instruments / timeframes / whether it is robust or a small-sample
artifact. NEW core/research/analyzer/ sub-package: baseline.py (read-only
BaselineOutcome view of an OpportunityRecord mapping the frozen 9A trade
facts onto the same outcome surface the metrics read -- filled/unsettled,
pnl, r (authoritative journal r or pnl/risk_amount), mae/mfe kept None
when the journal omits them, never fabricated); experiment_metrics.py
(reuses the frozen 9B lab.metrics formulas -- WIN := pnl>=0, PF := gross
profit / gross loss, expectancy := avg pnl, drawdown over an ordered
equity curve -- and augments total/avg/median R, gross profit-R / gross
loss-R, avg/median MAE and MFE, avg/median bars-to-entry; GROUPED
metrics / group sizes by direction / exchange / instrument / timeframe /
strategy / category / entry_model / experiment_id; zero denominators ->
0.0, PF inf-parity, never NaN); opportunity_analysis.py (category
distribution reusing ONLY the 9C classify_opportunity vocabulary; verbatim
rejection-reason distribution; missed-continuation counts);
recovery_analysis.py (RecoveryReport: per-opportunity deterministic
transition BASELINE-category -> EXPERIMENT-state composed from existing
tokens, e.g. REJECTED -> WIN / REJECTED -> LOSS / REJECTED ->
STILL_REJECTED / ENTRY_NOT_REACHED -> STILL_NOT_REACHED / MISSED_CONTINUATION
-> WIN / FILLED -> BETTER_RESULT / WORSE_RESULT / SAME_RESULT /
NOT_FILLED; recovered-unfilled opportunities preserved by canonical id;
COST of recovery: additional trades / wins / losses, incremental R and
PnL, recovery rate, profitable recovery rate, rejected-reason recovery
(verbatim reasons), missed-continuation ISOLATED not mixed); comparison.py
(ExperimentComparison: baseline-vs-experiment and experiment-vs-experiment
deltas -- incremental fills/wins/losses, incremental R/PnL, delta
expectancy / win-rate / PF / MAE / MFE, sample counts; inf-safe, never
NaN; retains exact config provenance + experiment_id; NEVER ranks or
promotes); robustness.py (deterministic lightweight assessment: minimum
sample, small-sample warning, no statistical-significance claim, loss
expansion, directional imbalance, in-sample-only -> OOS required -- no
statistical procedure implemented, no overfitting language);
experiment_matrix.py (ExperimentMatrix: composes the FROZEN 9B
ParameterGrid + the 9C-only outcome_bars dimension into deterministic
independent CounterfactualConfigs -- caller insertion order preserved,
base config never mutated, empty ranges yield zero combinations,
deterministic 9C experiment ids, unknown params fail loudly, no shared
state, never blended); research_report.py (ResearchReport: deterministic
BASELINE / EXPERIMENTS / RECOVERY / REJECTED / ENTRY_MODEL_COMPARISON /
DIRECTIONAL / METRICS / ROBUSTNESS / WARNINGS sections preserving exact
config provenance + machine-readable to_dict() + human render(), with an
explicit ANALYZER-NOT-OPTIMIZER statement); research_analyzer.py
(ResearchAnalyzer: orchestrates read-only analysis of records + bundles,
ALWAYS like-for-like per-experiment baseline restricted to the very
opportunities that experiment evaluated so incremental fills/wins/losses/R
are honest deltas; strict provenance guard -- every experiment must carry
its exact CounterfactualConfig or it fails loudly; convenience
analyze_results / run_and_analyze; simulation ALWAYS stays in 9C, the
analyzer only reads produced facts). ISOLATION: reads OpportunityRecords
+ counterfactual outcomes only; COUNTERFACTUAL provenance only; NEVER
mutates OpportunityRecord / CounterfactualConfig / CounterfactualOutcome /
Journal / TradeRegistry / Account / PortfolioState / SharedCapital;
no production / journal / ledger / portfolio mutation; 7E/7/8/8B/6C-6E
untouched. NO lookahead (analyzer never re-simulates; it only summarizes
9C's already-causal facts), NO optimization, NO ranking, NO parameter
promotion, NO ML/AI -- the analyzer reports evidence only, and any future
AI research layer consumes exactly this structured evidence. Tests:
tests/test_research_analyzer_9d.py (45): baseline metrics from record
facts (filled/settled/wins/losses/win_rate/PF/expectancy/total_R/avg_MAE/
avg bars-to-entry); experiment metrics over 9C outcomes (wins/losses/
total_R/net_pnl/expectancy with fill-based R verified); like-for-like
baseline vs experiment comparison (incremental fills=4 / wins=3 /
losses=1 / R=5.0 / pnl=10.0 / delta_expectancy); recovery classification
(REJECTED -> WIN/LOSS, ENTRY_NOT_REACHED -> STILL_NOT_REACHED and -> WIN,
MISSED_CONTINUATION -> STILL_MISSED and -> WIN isolated); rejected-reason
grouping verbatim (TOO_FAR_FROM_MARKET / INSUFFICIENT_RISK_WIDTH /
STALE_ZONE); result quality (FILLED -> BETTER_RESULT / WORSE_RESULT);
bullish/bearish and symbol grouping; category distribution reuses 9C
vocabulary; experiment-matrix determinism (insertion order, distinct
stable ids, outcome_bars participates in identity, empty range zero
combos, baseline-only config, unknown-key rejection, base config never
mutated); zero-denominator metrics (all zeros, never NaN); robustness
(small sample, loss-expansion warning, directional-imbalance warning,
balanced-direction no-warning); isolation / determinism (no blending,
identical across runs, COUNTERFACTUAL provenance preserved, config +
outcome objects not aliased between experiments); immutable inputs
(records + configs unchanged after analysis); fail tolerance (malformed
record -> NON_EVALUABLE warning, never aborts); empty experiment / empty
opportunity / fully-empty sets; multiple independent experiments with
distinct ids; exact config provenance preserved; analyze_results requires
exact config (fails loudly) and accepts a 9C-style dict; run_and_analyze
end-to-end through matrix + 9C runner + analyzer (rr=2 wins vs rr=3
unsettled on a shaped series); incremental R / cost of recovery surfaced
in the report; a REGEX import boundary proves the analyzer never touches
production internals. Proof: 9D 45/45 OK; compileall clean; full suite
823/823 OK (778 + 45 new; zero existing-test changes -- new package is
additive, no production edits, tracked .pyc restored before commit).
Docs: import_manifest.md added the EXPERIMENT MATRIX + RESEARCH ANALYZER
section (STATUS 121); project_manifest.md marks the analyzer modules
Active with an explicit NO-AI / NO-ML / NO-OPTIMIZER / NO-AUTO-PROMOTION /
NO-LOOKAHEAD / NO-LEDGER-MUTATION note. Commit: independent Phase 9D
milestone; the analyzer reports what happened under each explicitly
specified configuration and NEVER promotes one -- AI/ML research is
deferred to 9E/9F/9G, and no BREAKOUT/rules/7E results were modified.
 122. PHASE 9E -- RESEARCH INTELLIGENCE / RECOMMENDATION ENGINE (+43
tests; deterministic, research-only, NOT production optimization).
A read-only layer that CONSUMES a 9D ResearchReport (and, optionally,
the already-produced 9C CounterfactualOutcomes and confluence feature
records) and produces structured, explainable, evidence-backed research
RECOMMENDATIONS. It NEVER simulates (9C owns simulation, 9D owns
analysis), NEVER modifies strategy/execution/risk/portfolio/live-or-paper,
NEVER imports or invokes any AI/LLM/ML, NEVER auto-promotes, and NEVER
reinterprets the Phase 7E NO-GO as a production directive (directional
analysis stays research-only, never a directional production rule).
NEW core/research/intelligence/ sub-package:
recommendation_types.py (the closed, plain-string vocabulary:
RECOMMENDATION_STATUSES in {OBSERVATION, HYPOTHESIS, PROMISING,
INCONCLUSIVE, REJECTED, REQUIRES_OOS, BLOCKED} -- research labels that
NEVER mean production approval; RECOMMENDATION_CATEGORIES in {ENTRY_
RECOVERY, ENTRY_NOT_REACHED, MISSED_CONTINUATION, RR_ANALYSIS, EXPIRY_
ANALYSIS, ENTRY_OFFSET_ANALYSIS, STOP_TARGET_ANALYSIS, DIRECTIONAL_
ANALYSIS, SYMBOL_ANALYSIS, CONFLUENCE_ANALYSIS, GENERAL}; evidence grades
INSUFFICIENT_SAMPLE / SMALL_SAMPLE / LIMITED / MODERATE / STRONG; the 9D
robustness terms ROBUST / NON_ROBUST / OOS_REQUIRED / LOSS_EXPANSION /
DIRECTIONAL_IMBALANCE / NO_CLEAR_ADVANTAGE; RECOVERABLE_BASELINE_
CATEGORIES); recommendation.py (immutable Recommendation with a
deterministic recommendation_id = sha1 over category + candidate ids +
parameters_changed -- same evidence reproduces the same id, NO random
UUIDs -- plus baseline/candidate metrics, recovery facts, deltas,
robustness_status, sample_size, warnings and the recommendation_status);
evidence.py (EvidencePackage per candidate: exact experiment_id +
config provenance + baseline/candidate metrics + like-for-like comparison
+ recovery + robustness + sample_size, with a deterministic NON-statistical
evidence_strength grade by settled count, never 'significant');
opportunity_recovery.py (OpportunityRecoveryInsight: per-category recovery
from 9D recovery-transitions -- REJECTED/ENTRY_NOT_REACHED/
MISSED_CONTINUATION -> WIN / LOSS / STILL_* -- count-weighted,
distinguishing a recovered WIN (success) from a recovered LOSS (costs R,
never counted as a success), recovery_rate and successful_recovery_rate);
parameter_insights.py (per-parameter comparison of experiments that vary
along ONE config parameter -- rr/expiry/entry_offset/entry_offset_atr/
entry_model/stop_mode/target_mode/outcome_bars -- reported as MOVES not
'best', value ordering deterministic numeric-then-string, only params with
>1 distinct value are reported); directional_analysis.py (per-direction
BULLISH/BEARISH and per-symbol decomposition of 9D group metrics;
directional-imbalance flag propagated; symbol_breakdown flags whether an
advantage is broad or symbol-specific using read-only outcome metrics and
is honest 'no symbol breakdown ...' when no outcomes are supplied --
never fabricated); confluence_analysis.py (infrastructure for FUTURE
feature/confluence evidence -- Wyckoff/footprint/Fibonacci/flow/volume/
liquidity/market-structure/FVG/order-block/displacement/smart-money --
that works correctly with ZERO confluence data, reporting
CONFLUENCE_DATA_UNAVAILABLE and no fabricated feature rows, and passes
through supplied decision-time features read-only); robustness_gate.py
(deterministic robustness STATUS classifier folding 9D findings + recovery
cost + directional balance: INSUFFICIENT_SAMPLE / LOSS_EXPANSION /
OOS_REQUIRED / NON_ROBUST / ROBUST / INCONCLUSIVE -- never claims
significance, never blocks/enables production); hypothesis.py
(deterministic Hypothesis objects -- traceable, id-stable, one per
recommendation plus directional-imbalance / OOS caveats -- the structured
input a future AI interpreter consumes); research_intelligence.py
(ResearchIntelligence orchestrator over a 9D report + optional
outcomes_by_experiment and confluence -> an immutable IntelligenceReport
with recommendations sorted by id, an EvidencePackage list, confluence,
insights (recovery/parameter/directional/symbol), hypotheses, and a
deterministic LEAD chosen as the first of PROMISING / REQUIRES_OOS /
HYPOTHESIS; report to_dict() carries a standing NON-PRODUCTION reminder
and render() is deterministic). RECOMMENDATION STATUS is a research
label, not an approval: BLOCKED when no usable experiment bundles,
OBSERVATION when the candidate matches the baseline band, HYPOTHESIS for
a small-sample or recovery-only advantage, PROMISING when the candidate
beats baseline + material recovery + no loss-expansion + robust,
INCONCLUSIVE when no comparison is available, REQUIRES_OOS whenever an
in-sample advantage still needs OOS validation, REJECTED when the
candidate LOSES to baseline on filled/R/expectancy/win-rate/PF.
Confluence is NEVER fabricated; with zero features it reports
CONFLUENCE_DATA_UNAVAILABLE and the report is still complete. Tests:
tests/test_research_intelligence_9e.py (43): evidence-strength bands and
non-statistical grading; EvidencePackage provenance + determinism;
robustness gate (insufficient-sample / loss-expansion-by-wins-and-by-
warning / directional-imbalance-non-robust / small-sample-advantage-
requires-oos / robust / no-advantage-with-warnings-non-robust /
no-advantage-no-warnings-inconclusive); recommendation_id determinism +
frozen Recommendation + statuses-are-labels-not-approval; opportunity
recovery WIN vs LOSS vs STILL with count-weighted transitions and
recovery/successful-recovery rates; confluence zero-data-unavailable /
feature passthrough / supplied-only-values; parameter insight only-varying-
param + numeric/string-ahead ordering + skip-non-varying; directional
breakdown insufficiency flag + imbalance flag; symbol breakdown
broad-vs-symbol-specific + no-data-honest; hypotheses deterministic-sorted
and directional-imbalance caveat; end-to-end ResearchIntelligence
(empty-report->BLOCKED, full-report categories, lead selection,
REJECTED candidate, OBSERVATION when unchanged, source-not-mutated,
symbol-insight via READ-ONLY real 9C outcomes, confluence pass-through and
never-fabricated, serialization roundtrip with reminder, render, run-to-run
determinism); REAL 9D integration (ResearchAnalyzer -> ResearchIntelligence
end-to-end on real BREAKOUT_CONTINUATION outcomes); REGEX import boundary
proving the intelligence package never imports production internals / any
AI-ML library / simulation and never claims statistical significance, plus
the serialized report always ships the NOT-a-production-directive reminder.
Proof: 9E 43/43 OK; compileall clean; full suite 866/866 OK (823 + 43 new;
zero existing-test changes -- additive package only, no production edits,
tracked .pyc restored before commit). Docs: import_manifest.md added the
PHASE 9E section (STATUS 122, position before _ARCHIVE); project_manifest.md
marks the intelligence modules Active with an explicit NO-AI / NO-ML /
NO-OPTIMIZER / NO-AUTO-PROMOTION / NO-LOOKAHEAD / RESEARCH-ONLY /
NEVER-FABRICATE-CONFLUENCE note. Commit: independent Phase 9E milestone; the
intelligence engine interprets 9A-9D evidence into recommendations and
explicitly packages evidence for a future 9F (Confluence/Feature Evidence)
and 9G (ML) layer; no BREAKOUT/rules/7E/production results were modified.
  123. PHASE 9F -- CONFLUENCE / FEATURE EVIDENCE (+45 tests; deterministic,
   research-only evidence layer that makes later 9G ML / AI meaningful).
   A decision-time, NO-LOOKAHEAD feature snapshot is recorded per
   opportunity at its EXACT decision bar (a bounded CausalWindow of bars
   strictly index < decision_bar; the decision bar itself is never a
   feature source), then canonical confluence / market-structure /
   technical features are derived deterministically, and the produced
   evidence is joined to the already-labelled 9C/9D outcomes into read-only
   CORRELATION tables. It NEVER simulates (9C owns simulation), NEVER
   touches strategy/execution/risk/portfolio/live-or-paper, NEVER imports
   or invokes AI/ML, NEVER auto-promotes, NEVER fabricates an unavailable
   feature, and NEVER quietly turns the Phase 7E NO-GO directional
   hypothesis back into a production rule (direction/size/action are never
   emitted as an instruction -- a snapshot is evidence, not a directive).
   NEW core/research/features/ sub-package:
   causal_window.py (deterministic, immutable CausalWindow/CandlePoint +
   extract_causal_window(candles, decision_bar, lookback): bounded history
   strictly before the decision bar, missing volume tolerated as None and
   NEVER fabricated, non-price/invalid OHLC rows dropped; the window never
   mutates its inputs); indicators.py (pure, data-gated deterministic
   indicators ATR / SMA / EMA / rolling_volatility / bollinger_position /
   OBV -- each returns UNAVAILABLE (None) when the bounded series is too
   short or misaligned, including OBV returning the accumulated total only
   on aligned equal-length close/volume series); confluence_features.py
   (13 deterministic producers -- wyckoff_phase, market_structure,
   atr_regime, bollinger_position, sma_slope, obv_trend, liquidity_sweep
   (direction-correct stop-side sweep + reclaim), fvg_present (directional
   fair-value gap), displacement_strength, order_block, fibonacci_zone
   (0.382/0.5/0.618 swing band the ENTRY sits in), and volume_profile and
   footprint_flow which return UNAVAILABLE because no order-flow /
   volume-profile data stream exists -- never synthesized); feature_
   snapshot.py (immutable FeatureSnapshot: preserves the opportunity's OWN
   decision-time entry/stop/target/atr + direction/instrument/timeframe/
   decision_bar/WindowSize + the deterministic feature map, with
   available_feature_count()); dependency_analysis.py (build_dependency ->
   DependencyAnalysis of per-feature, per-VALUE buckets: entry_reached_rate,
   rejected->recovered_rate (via supplied recoveries / outcome recovered),
   missed_continuation_count (via category), WIN/LOSS win_rate, avg_R,
   avg_MAE, avg_MFE, direction and symbol segmentation; buckets with ZERO
   outcome evidence report n but NEVER fabricate win_rate/R/rates (None);
   deterministic value ordering and table ordering -- CORRELATION OF
   EVIDENCE only, never causation, never ML); feature_analyzer.py
   (FeatureAnalyzer orchestrator: snapshot(record, candles) + analyze(...)
   -> immutable FeatureEvidenceReport with snapshots, a ConfluenceAnalysis
   fed into the FROZEN 9E surface (name/value/sample/outcomes/experiment_id
   rows), and the DependencyAnalysis; when NO feature can be derived the
   analysis reports CONFLUENCE_DATA_UNAVAILABLE -- it never claims
   confluence that does not exist; concatenates the render() contract);
   __init__.py exposing the 9F public surface. Tests:
   tests/test_research_features_9f.py (45): causal window no-lookahead
   (bars strictly < decision_bar, bounded by lookback, empty window, missing
   volume not fabricated); deterministic data-gated indicators (OBV
   accumulation and misalignment, Bollinger position in-band, short-window
   ATR/Bollinger UNAVAILABLE, SMA determinism); confluence producers (empty
   and short windows -> all UNAVAILABLE not fabricated, footprint/volume-
   profile always UNAVAILABLE, liquidity sweep direction-correct + reclaim,
   FVG directional, displacement, OBV trend signed/absent-without-volume,
   registered producers, cross-run determinism); snapshot decision-time
   preservation + decision-bounded features; dependency tables (entry-reached
   rate, rejected->recovered rate, missed-continuation, WIN/LOSS + avg_R +
   avg_MAE + avg_MFE, direction + symbol segmentation, missing-outcome never
   fabricates win_rate/R, whitelist filtering, deterministic ordering,
   to_dict shape); 9E ConfluenceAnalysis integration (feeds rows,
   CONFLUENCE_DATA_UNAVAILABLE when zero features, deterministic dict/render,
   never mutates records/candles); REGEX boundary proving the package never
   imports production internals / AI-ML / simulation / a future provider, all
   producers data-gated, and the 7E NO-GO stays untouched (no action/size/
   approve instruction in a snapshot).
   Proof: 9F 45/45 OK; compileall clean; full suite 911/911 OK (866 + 45 new;
   zero existing-test changes -- additive package only, no production edits,
   tracked .pyc restored before commit). Docs: import_manifest.md added the
   PHASE 9F section (before the 9E section) and project_manifest.md adds the
   features modules Active with an explicit NO-AI / NO-ML / NO-SIMULATION /
   NO-LOOKAHEAD / NEVER-FABRICATE / RESEARCH-ONLY / 7E-NO-GO-UNTOUCHED note.
   Commit: independent Phase 9F milestone; the deterministic decision-time
   feature + correlation layer supplies the exact feature values observed at
   each decision point for the later 9G statistical/ML research layer; no
   BREAKOUT/rules/7E/production results were modified.
  124. PHASE 9G -- ML / STATISTICAL RESEARCH LAYER (+45 tests; STATISTICAL
   relationships are DISCOVERED; 9G does NOT decide what gets traded).
   The dependency-isolated research layer that consumes the 9F decision-time
   FeatureSnapshots + 9C/9D outcomes and produces deterministic,
   chronologically-split statistical / simple-ML / feature-interaction /
   opportunity-recovery research -- the evidence that makes the later 9H
   autonomous AI researcher meaningful. It is STRICTLY research-only: never
   touches strategy/execution/risk/portfolio/live-or-paper, never auto-
   promotes, never emits a trade directive, never imports production
   internals or any deep-AI dependency, and every result is framed as
   ASSOCIATION (never causation, never a trade decision). NO-TEMPORAL-
   LEAKAGE: the dataset is split chronologically (TRAIN | VALIDATION | OOS
   and expanding-window walk-forward) with no random shuffling; the 9F
   decision-time rule (features only from candles strictly < decision_bar)
   is inherited -- no future information enters any feature vector. First-
class OPPORTUNITY RECOVERY RESEARCH: rejected / ENTRY_NOT_REACHED /
    MISSED_CONTINUATION opportunities -> their feature snapshot -> recovery
    probability + expected R/MAE/MFE over recovered outcomes + the proposed
    alternative entry / RR / expiry / model. DEPENDENCY ISOLATION (contract):
   the production/paper engine and the whole product install, compile, test
   and run with sklearn/scipy ABSENT (confirmed: not installed in this env);
   every statistical baseline is pure math/numpy; the simple-ML backends
   (logistic regression, decision tree) are pure-numpy and deterministic;
   sklearn (logistic/tree/random-forest) is an OPTIONAL guarded backend that
   degrades to ML_BACKEND_UNAVAILABLE when absent -- the research stack is
   never a production dependency.
   NEW core/research/ml/ sub-package: split.py (deterministic chronological
   temporal_split TRAIN|VALIDATION|OOS + expanding-window walk_forward (fold
   order by decision_bar/timestamp/list order; no shuffle, no overlap, train
   strictly ends before test -- no temporal leakage)); statistics.py (9G.1:
   StatisticalBaseline -- n / wins / losses / unsettled_rate / win_rate /
   loss_rate / entry_reached_rate / avg_R / expectancy / avg_MAE / avg_MFE /
   deterministic R-distribution bins; effect_size_h / effect_size_d; cond-
   itional_statistics P(WIN | feature=value), P(ENTRY_REACHED | value),
   P(POSITIVE_R | value) with effect-size-vs-overall -- honest None on zero
   denominator, never fabricated); models.py (9G.2: encode_target for the
   closed targets ENTRY_REACHED / WIN / POSITIVE_R / EXPECTED_R /
   RECOVERY_SUCCESS with an available-mask excluding unsettled (never
   fabricated); NumpyLogisticRegression (deterministic fixed-iteration L2
   GD, zero-init) and NumpyDecisionTree (deterministic greedy info-gain) --
   ALWAYS available; SimpleModel wrapper with 'numpy' (always) or 'sklearn'
   (only when installed) backends; sklearn probed lazily inside a guarded
   try/except -> ML_BACKEND_UNAVAILABLE; pure-numpy rank-sum AUC (ties get
   mean rank) returning None on a single-class target); interaction.py
   (9G.3: interaction_analysis builds ASSOCIATION tables ONLY over feature-
   value combos actually observed -- e.g. Wyckoff + FVG + OB + Fibonacci +
   volatility + liquidity_sweep -> ENTRY_REACHED% / WIN% / avg R / avg MAE /
   avg MFE / n / sufficient_sample; absent/partial combos not reported;
   tiny samples honestly flagged, rates None not fabricated);
   analyzer.py (MlAnalyzer -> immutable MlResearchReport: chronological
   split + walk-forward + 9G.1 baseline/conditional + 9G.2 ML fit on TRAIN
   scored on VALIDATION/OOS AUC + 9G.3 interaction + recovery research;
   to_dict() carries association_not_causation + no_trade_directive +
   backend; render() deterministic and carries the association-only
   reminder); __init__.py exposing the 9G public surface.
   Tests: tests/test_research_ml_9g.py (45): temporal splitting chronological /
   unshuffled / non-overlapping / expanding walk-forward / run-to-run
   deterministic / re-orders by decision_bar; 9G.1 baseline math (win/loss/
   unsettled, expectancy, avg R/MAE/MFE, R-bins, effect sizes, conditional
   WIN/ENTRY_REACHED) + honest-None-on-zero-denominator; 9G.2 encode_target
   WIN/LOSS masks unsettled, ENTRY_REACHED/POSITIVE_R/RECOVERY_SUCCESS,
   numpy logistic + tree deterministic and classify, SimpleModel-numpy trains,
   AUC rank-sum correct + single-class None, backend_status in {sklearn,
   ML_BACKEND_UNAVAILABLE} + sklearn-absent graceful degradation; 9G.3
   interaction only-occurring-combos + tiny-sample honesty + missing-outcome
   nulls + partial-combo exclusion + rates/avg-R shape; MlAnalyzer full report
   (phase/split/no-leakage/baseline/ml_results/walk-forward), train-only
   chronological fit, first-class recovery (REJECTED/ENTRY_NOT_REACHED/
   MISSED_CONTINUATION candidates -> recovery_rate/expected_R/alternative
   passthrough), association-only framing (no action/size/approve anywhere),
   deterministic dict/render, closed TARGETS vocabulary, accepts real 9F
   FeatureSnapshot; REGEX/fs boundaries proving no production internals, no
   deep-AI (torch/tf/keras/xgboost/lgbm/mlx etc.), sklearn only inside the
   guarded models.py try/except, NO production module ever imports
   core.research.ml, no simulation, no auto-promotion, 7E NO-GO untouched.
   Proof: 9G 45/45 OK; compileall clean; full suite 956/956 OK (911 + 45 new;
   zero existing-test changes; numpy-only env, sklearn/scipy ABSENT -- the
   isolation contract is exercised by the suite itself, docs: import_
   manifest.md Phase 9G section before the 9F section; project_manifest.md
   marks the ml modules Active with ML-DISCOVERS-NOT-DECIDES / NO-AUTO-PROMO /
   NO-LOOKAHEAD / NO-PRODUCTION-IMPORT / SKLEARN-OPTIONAL / RESEARCH-ONLY /
   7E-NO-GO-UNTOUCHED note). Commit: independent Phase 9G milestone; the
   deterministic statistical + simple-ML + interaction + recovery research
   layer over the 9F feature evidence is the dataset/evidence foundation the
   9H autonomous AI researcher consumes; no
   BREAKOUT/rules/7E/production results were modified.

125. **9H Autonomous AI Researcher Core** (provider-neutral, research-only
   scientist). core/research/researcher/: types.py (EvidenceContext/
   Hypothesis/ExperimentResult/ResearchRecommendation/InvestigationReport +
   closed experiment vocabulary + STANDING_LIMITATION), providers.py
   (AIProvider ABC + always-available deterministic NullProvider with
   evidence-gated rule drafts that never conjecture; guarded OpenAI/Anthropic/
   OpenRouter/Ollama stubs that degrade to PROVIDER_UNAVAILABLE when the SDK
   is absent -- the engine runs with zero external AI), memory.py (persistent
   ResearchMemory: sha1 question-fingerprint, record/recall/dedup/next_
   suggestion, optional atomic JSON with corrupt-file->fresh), planner.py
   (evidence-gated ONLY the supported 9B/9C experiment vocabulary --
   unsupported params/entry-models/expiry fail loudly -- deterministic sha1
   hypothesis ids H+10hex, memory dedup, deterministic sort), experiments.py
   (ExperimentExecutor/ExperimentRun drives the FROZEN 9C CounterfactualRunner
   .grid -> 9D ResearchAnalyzer -> 9E ResearchIntelligence -> 9F Statistical
   Baseline + temporal_split OOS fold + guarded FeatureAnalyzer, per-bundle
   ExperimentResult with exhaustive categories/statistical/oos/features),
   evaluate.py (EvidenceEvaluator ladder VALIDATED/HYPOTHESIS/REJECTED/
   INSUFFICIENT_EVIDENCE/OBSERVATION: MIN_VALIDATION_SETTLED=30 + MIN_OOS_
   SETTLED=5 + a 9E robustness gate that can never be bypassed; OOS-negative
   or OOS-too-small or robustness-flagged result downgrades VALIDATED and is
   never guessed as passing; sha1 recommendation ids R+10hex; evidence package
   only - failed experiments retained, nothing pruned), researcher.py
   (build_context + AutonomousResearcher.investigate returns InvestigationReport
   with the full evidence chain DATASET->HYPOTHESIS->EXPERIMENT->RECOMMENDATION
   ->LIMITATION, INSUFFICIENT_EVIDENCE when under-powered, research-only,
   production_ready=False always, records never mutated), __init__.py exports.
   Proof: tests/test_researcher_9h.py 37/37 OK (evidence context, providers
   incl. no-SDK run, planner determinism + unsupported-param/entry-model fail-
   loud + dedup, evaluator ladder incl. OOS-cannot-be-bypassed + robustness-
   downgrade + insufficient + retention, memory record/recall/dedup/next_
   suggestion/JSON/corrupt-file, e2e VALIDATED evidence chain + deterministic
   investigation + memory dedup second-run + tiny/vacuous->INSUFFICIENT +
   OOS-tail-cannot-bypass + failed-experiments-retained + records-never-
   mutated, boundary tests proving no production internals imported + no top-
   level AI-SDK imports + no order/ledger tokens + default base config
   supported). Invariants: NO production imports at any line; NO order/
   ledger/placement; NO lookahead; NO auto-promotion; conclusions always cite
   evidence or INSUFFICIENT_EVIDENCE (never guessed); 7E NO-GO untouched.
   Commit: independent Phase 9H milestone -- the autonomous researcher core
   consuming the frozen 9B-9G evidence; no BREAKOUT/rules/7E/production
    results modified.

126. **9I Unified Research Dataset / Knowledge & Data Intelligence**
   (core/research/dataset/ -- 4 modules). Normalizes every frozen 9A-9H
   surface into a single queryable ResearchDataset: row.py defines
   ResearchRow (frozen dataclass; stable deterministic sha1 row_id,
   DatasetSource closed vocabulary JOURNAL/COUNTERFACTUAL/ANALYSIS/
   INTELLIGENCE/FEATURE/ML/RESEARCH, observation_id join key, identity
   fields for grouping (instrument/direction/timeframe/strategy/category/
   result), two evidence bags (kv: descriptive parameters, measured:
   quantitative outcomes), to_dict / row_from_dict round-trip);
   collectors.py builds read-only normalization functions for all 9A-9H
   artifacts (collect_journal/collect_counterfactual/collect_analysis/
   collect_intelligence/collect_features/collect_ml/collect_researcher --
   each returns a deterministic ResearchRow tuple; inputs never mutated);
   dataset.py provides ResearchDataset append-only container with dedup,
   deterministic JSON persistence (atomic tmp+replace), corrupt-file-
   >fresh, and filtered access; queries.py provides entry_pipeline_
   breakdown (structurally valid vs entered, category split, rejection
   reasons, win rates), recovery_candidates (which missed/rejected
   observations could have been profitable under alternative 9B/9C
   configs, recovered R, captured-vs-missed economics, alternative
   config evidence), unify_by_observation (cross-source join by
   observation_id), aggregate (generic group-by / count / sum / mean /
   win_rate with insert-order determinism), answer_context (compact
   evidence dict for 9H). Proves the knowledge question: "of 800
   structurally valid setups, why only 200 entered, and of the 600
   missed, which could have been captured profitably?"
   Proof: tests/test_researcher_9i.py 19/19 OK (row determinism +
   round-trip, all 7 collectors, dataset dedup + persist/corrupt->
   fresh + inputs-never-mutated, entry pipeline breakdown determinism,
   recovery candidate join + economics + config evidence, cross-source
   unify, aggregate win_rate, answer_context, boundary no-production-
   imports + no-order-tokens + no-random-ids). Invariants: NO production
   imports at any line; NO order/ledger/placement; NO lookahead; NO auto-
   promotion; NO random/UUID/timestamps; 7E NO-GO untouched.
   Commit: independent Phase 9I milestone -- the unified knowledge layer
   giving 9H and future 9J+ the evidence tables to autonomously reason
about entry gaps and alternative configurations; no BREAKOUT/rules/
    7E/production results modified.

128. **9K Regime / Conditional Opportunity Discovery** (autonomous,
    deterministic, research-only "under-which-market-conditions" engine over
    the frozen 9A-9J layers). core/research/regime/: regime_types.py (closed
    dimension vocabularies TREND/RANGE, BULLISH/BEARISH/NEUTRAL, HIGH/NORMAL/
    LOW, EXPANSION/NEUTRAL/CONTRACTION, STRONG/NORMAL/ABSENT, SWEEPED/NORMAL,
    PRESENT/ABSENT + Wyckoff; frozen MarketRegime with data-gated
    UNAVAILABLE, RegimeObservation, ConditionalCell, ConditionalFinding whose
    is_production_directive raises ValueError + deterministic K+10hex id,
    FeatureSplit, WalkForwardWindow/Summary; REGIME_DIMENSIONS +
    PRIMARY_REGIME_DIMENSIONS), indicators.py (pure decision-time regime
    indicators reusing the frozen features.indicators atr/sma/volatility:
    trend_vs_range via normalised SMA-slope + span/ATR, direction_structure
    via pivot HH+HL vs LH+LL, volatility_regime (1.3/0.7), atr_regime
    (1.2/0.8), displacement_strength, liquidity sweep+reclaim, fvg shadow
    gap, order_block consolidation break, wyckoff_phase; every indicator
    data-gated -> UNAVAILABLE on thin windows), detector.py (detect_regime
    window ENDS AT the decision bar -- no lookahead; closed vocabulary +
    validate_dimension), segmenter.py (9A records -> RegimeObservation via
    frozen 9C classify_opportunity + decision-time regime; no decision bar ->
    honest empty regime; in_cell/cell_labels/regime_coverage/by_category),
    conditional.py (_validate_candidate strict 9B vocabulary -- fail loud on
    unknown axes/entry models, build_config = frozen base + scalar overrides,
    conditional_discovery: candidate vs frozen baseline inside EVERY cell +
    recoveries + delta + split breadth; statuses CONDITIONAL/CONDITIONAL_WEAK/
    INCONCLUSIVE/NOT_SUPPORTED, EVERY cell and finding retained -- no hiding
    of negative results; feature_splits observed-only 9F, min-sample gated),
    walkforward.py (temporal_windows chronological expanding-train/trailing-
    test, no shuffle; validate_conditional survival = majority of ADEQUATE
    windows positive AND above baseline with min_validation_n; thin windows
    counted honestly), multiple_testing.py (Sidak familywise corrected alpha,
    required_min_n = min_cell_n + ceil(log2(1+H)); findings flagged "possible
    lucky combination / insufficient after correction" -- retained, never
    hidden), engine.py (OpportunityDiscoveryEngine.run -> RegimeReport: segment
    -> conditional -> walk-forward -> splits -> multiple-testing -> robustness
    -> limitations; next_research = 9M multi-period OOS / 9L advanced ML+
    regime / 9N recommendation layer), report.py (frozen RegimeReport,
    report_id K+10hex, is_production_ready ALWAYS False and ValueError-guarded,
    emission_check proves NEVER_EMITTED tokens absent). Proof:
    tests/test_researcher_9k.py 91/91 OK (each indicator threshold + data-gate
    UNAVAILABLE + determinism, closed vocabulary/validate_dimension, segmenter
    decision-bar preference + honest no-decision-bar regime + no-lookahead
    (divergent futures byte-identical up to the decision bar), conditional
    fail-loud unknowns + every-label retention + exact e2e cell economics
    TREND +2.0R/-1.0R / RANGE -1.0R/+2.0R split breadth 6.0 + CONDITIONAL/
    NOT_SUPPORTED statuses + INCONCLUSIVE small-population retention +
    finding_id determinism + ConditionalFinding production-directive
    ValueError, feature-split gating/effect-size, walk-forward chronology +
    survival + thin-window counting + material-only validation, Sidak math +
    required_min_n + survive flags, engine e2e determinism/byte-identical
    rerun/emission-check/frozen report/empty-dataset honesty/robustness
    coverage, no production imports + no random/uuid/datetime + import-boundary).
    Invariants: no production imports; no orders/ledger; no lookahead;
    deterministic; every finding retained; research-only, never a promotion
    token. Commit: independent Phase 9K milestone -- regime / conditional
    opportunity discovery over the frozen evidence; no BREAKOUT/rules/7E/
    production results modified.

129. **9L Advanced ML + Regime / Opportunity Discovery** (autonomous,
    deterministic, research-only conditional-ML evidence layer fusing the
    frozen 9G stats/ML machinery with the frozen 9K regime framework).
    core/research/conditional_ml/: types.py (CANDIDATE_ALTERNATIVES = EXACTLY
    the 3 fixed production-supported entry models LIMIT_RETEST /
    MARKET_CONFIRMATION / BREAKOUT_CONTINUATION -- a fixed research grid,
    deliberately NOT auto-ML optimizer; frozen OpportunityContext (regime at
    decision + counterfactual fill bar, 9F decision-time features, baseline
    entry state), RecoveryFinding, AlternativeEvidence, EntrySelection,
    InteractionFinding, TransitionFinding, SymbolBehaviour, CalibrationBin/
    Summary, deterministic L+10hex finding ids), guards.py (required_min_n
    grows via log2 over the TOTAL enumerated hypothesis family,
    familywise_alpha Sidak, holm_survives Holm-Bonferroni step-down,
    z_prop_win/z_mean_diff two-sided TAIL p-values via pure math.erf -- never
    inverted, strong evidence -> small p), probabilities.py (fixed-form
    additive-logit OutcomeModel trained ONCE on TRAIN, clipped/clamped,
    deterministic, no hyper-parameter search), contexts.py (opportunity ->
    OpportunityContext at decision time, cannon decision-bar rule, 9F feature
    snapshot, entry state; windows END AT every decision/fill bar -- no
    lookahead), recovery.py (recovery probability for MISSED/REJECTED
    baselines, each fixed alternative replayed by 9C, non-fill counts as a
    failed recovery -- no fabrication; RECOVERY_SUPPORTED only when the
    raised min-n gate passes AND expected R positive), entries.py (conditional
    ENTRY-MODEL selection per (regime, direction) cell: every alternative
    with its own trained model must clear OOS sample gate + OOS expectancy
    >= baseline + economic margin AND survive the GLOBAL familywise
    correction; otherwise INCONCLUSIVE with EVERY alternative row RETAINED),
    interactions.py (regime-conditional feature interactions over the fixed
    bounded roster, size-2/3 only, same-feature combos structurally excluded,
    hard cap 100 reported when reached, SUPPORTED only when the effect
    carries TRAIN->OOS with same sign AND |Cohen's d| >= EFFECT_D_MIN),
    transitions.py (generated-regime -> filled-regime table; stable buckets
    always STABLE, CHANGED only on material expectancy delta), symbols.py
    (symbol x primary-regime cells, justified only when n >= raised gate AND
    expectancy >= global + margin; every cell retained), calibration.py
    (equal-width OOS-only bins all retained -- a gap is a finding -- ECE/
    Brier/slope, CALIBRATED only when OOS >= gate AND ECE within the closed
    bound), engine.py (ConditionalMlEngine.run(opportunities, candles,
    config) -> frozen ConditionalMlReport: contexts -> fixed 3-alternative
    grid replay via 9C CounterfactualRunner with baseline measured as the
    genuine BREAKOUT_CONTINUATION counterfactual, chronological
    temporal_split TRAIN|VALIDATION|OOS, TOTAL hypothesis enumeration, every
    surface runs, then the GLOBAL multiple-testing guard (Sidak across the
    whole family + Holm within interactions) and frozen-safe
    survival/justified flags injected via dataclasses.replace; robustness
    (pipeline order, chronological split, fixed grid, combinatorial cap) +
    limitations), report.py (frozen ConditionalMlReport, report_id L+10hex,
    is_production_ready ALWAYS False and ValueError-guarded, emission_check
    proves NEVER_EMITTED tokens absent from the report body). Proof:
    tests/test_researcher_9l.py 39/39 OK (fixed alternative grid + closed
    vocabulary, required_min_n/familywise_alpha Sidak exact math + holm step-
    down + two-sided tail p-values, OutcomeModel training/calibration shape
    agreement, default gates, context decision-time regime + fill-time regime
    + 9F features + no-lookahead boundary, recovery exact SUPPORTED/
    INCONCLUSIVE figures, conditional entry selection SUPPORTED/INCONCLUSIVE
    with baseline counterfactual delta, interaction SUPPORTED train->OOS
    sign + effect + gated term, transition stable/CHANGED semantics,
    symbol justified gating, calibration CALIBRATED/CALIBRATION_GAP ECE-Brier-
    slope, engine e2e canonical numbers (report_id Le7f171194a, 54
    opportunities, recovery 6, entry cells 2, interactions 0, transitions 2,
    symbols 3, calibration 3, total_hypotheses 223, corrected_alpha 0.00023,
    n_survive 0) + byte-identical determinism rerun + frozen report +
    production ValueError + empty-input honesty + robustness + no production
    imports/no random-uuid-datetime-scipy-sklearn/import-boundary +
    promotion tokens absent from report body).
    Invariants: no production imports; no orders/ledger; no lookahead
    (decision/fill-time only); deterministic; fixed bounded grid (no
    unbounded search); every finding retained; pure-python probability path;
    research-only, never a promotion token. Commit: independent Phase 9L
    milestone -- advanced ML + regime/opportunity discovery over the frozen
    evidence; no BREAKOUT/rules/7E/production results modified.

130. **9M Multi-Period Out-of-Sample Validation** (autonomous, deterministic,
    research-only multi-period OOS replay layer over the frozen 9K/9L
    discoveries). core/research/oos/: constants.py (closed vocabulary:
    per-period VALIDATED/PROMISING/INCONCLUSIVE/REJECTED/UNAVAILABLE, finding
    ladder BLOCKED->UNAVAILABLE->INCONCLUSIVE->REJECTED->OOS_PARTIAL->
    OOS_PROMISING->OOS_ROBUST->VALIDATED_RESEARCH_ONLY; locked defaults
    OOS_PERIODS 6, DISCOVERY_FRACTION 0.5, MIN_OOS_OPPORTUNITIES/TRADES 30/10,
    MIN_TOTAL_OOS_TRADES 60, MIN_SURVIVING/SIGN_CONSISTENT 5, PURGE/EMBARGO 0,
    split protocol frozen), oos_types.py (frozen HypothesisOosResult/OosSummary
    + economic_statistics/survival_ratio, scalar-safe to_dict), period.py
    (partition + OosPartition + outcome_leakage NOT_REQUIRED/PROTECTED/
    UNAVAILABLE), validator.py (evaluate_pool -> evaluate_period with
    CANDIDATE_ALTERNATIVES replay against the genuine 9C baseline
    counterfactual; n_candidate_filled counts fills, not rate), aggregator.py
    (summarize_periods + final_status ladder + multiple_testing Sidak + per-
    period summary), robustness.py (classify LOW/MEDIUM/HIGH with passes/
    reasons; per-symbol/per-direction/per-regime evidence separated, never
    merged), engine.py (OosValidationEngine.run(opportunities, candles, config,
    hypotheses) -> frozen OosReport: chronological partition of the trailing
    50% into 6 OOS periods, per-period sub-evals (regime target/non-target,
    symbols, directions), survival/sign/economic gates, corrected total-trades
    gate via guards.required_min_n over the family, leak-guard PROTECTED when
    horizon+gap into future, 7E -> BLOCKED, unknown gate keys raise),
    report.py (frozen OosReport + build_report, deterministic M+10hex
    report_id, is_production_ready ALWAYS False and ValueError-guarded,
    emission_check returns (False, reason), NEVER_EMITTED promotion tokens
    never in the report body). Proof: tests/test_researcher_9m.py 37/37 OK
    (protocol surface + familywise Sidak exact math incl. family-2
    corrected_alpha 0.025320565519103666, partition math with 864/432/432/6
    + boundaries of 72, aggregator ladder REJECTED/OOS_PARTIAL/OOS_PROMISING/
    INCONCLUSIVE/OOS_ROBUST/VALIDATED_RESEARCH_ONLY via final_status units,
    recovery unit INCONCLUSIVE (40 R records, n_recovered 40, capture_gain
    1.0), canonical e2e report_id Me686dca76c wf-true / M8be132b4e4 wf-false
    with 6/6 VALIDATED + HIGH robustness + familywise true + leak PROTECTED,
    7E BLOCKED, SHORT UNAVAILABLE, bounds INCONCLUSIVE via gate override,
    byte-identical determinism + no-lookahead future-bar mutability rerun +
    no random-uuid-datetime-scipy-sklearn + no production imports +
    promotion tokens absent from report body). Invariants: no production
    imports; no orders/ledger; no lookahead (decision/fill-time only);
    deterministic; chronological only, no shuffle, split never re-optimized;
    every per-period result RETAINED in the report; research-only, never a
    promotion token. Commit: independent Phase 9M milestone -- multi-period
    out-of-sample validation over the frozen 9L/9K discoveries; no
    BREAKOUT/rules/7E/production results modified.

132. **9O Research UX: Recommendation Readback** (autonomous, deterministic,
    research-only explanation layer that turns the frozen 9N
    RecommendationReport into a human-usable readback of WHY each
    recommendation exists, what evidence supports it, what failed, what
    remains uncertain, and exactly why it is still research-only --
    consuming ONLY the frozen 9N report and never re-running OOS /
    conditional ML / regime). core/research/readback/: constants.py
    (closed RESEARCH_VERDICTS SEVEN_E_BLOCKED / NO_EVIDENCE / INCONCLUSIVE /
    REJECTED / REQUIRES_MORE_OOS / CONDITIONAL / PROMISING /
    VALIDATED_RESEARCH_FINDING -- the MAXIMUM possible statement, with NO
    TRADABLE member by construction; PRODUCTION_STATUS always
    RESEARCH_ONLY; closed UNCERTAINTY_ROSTER + NEGATIVE_EVIDENCE_ROSTER;
    NEVER_EMITTED TRADABLE_STRATEGY / TRADABLE-GO / PRODUCTION_READY),
    types.py (frozen ReadbackEntry -- research_verdict, evidence_status,
    claim, rationale, per-aspect evidence dict, closed uncertainty tags,
    production_status; frozen ReadbackReport -- deterministic O+10hex
    report_id from a canonical payload EXCLUDING report_id, stable under
    reordered entries, is_tradable property always False, emission_check()
    dict verifying the boundary against the ACTUAL serialized body), explain.py
    (verdict_for_9n_status: total injective 9N -> 9O mapping where the top
    9N tier ROBUST_RESEARCH_FINDING maps to VALIDATED_RESEARCH_FINDING --
    never TRADABLE_STRATEGY; explain_entry / explain_report: 1:1
    recommendation -> ReadbackEntry pairing joined on the shared
    (hypothesis_id, oos_report_id) key the 9N finding and its flattened
    recommendation both carry; build_readback constructor/validator
    normalizes + sorts, validates verdicts and uncertainty tags, forces
    production_status RESEARCH_ONLY). The core boundary: VALIDATED_RESEARCH_
    FINDING is allowed (a research artifact), TRADABLE_STRATEGY is
    impossible at this boundary by construction. Proof:
    tests/test_researcher_9o.py 48/48 OK (closed verdict vocabulary with
    no tradable member + entry/report reject tradable verdict, total
    injective 9N->9O verdict mapping, 1:1 entries == recommendations +
    joined evidence from the frozen finding, aspect coverage OOS/regime/
    discovery/counterfactual/baseline/supporting-metrics/negative, closed
    uncertainty + negative-evidence tags, deterministic report id + rerun +
    reordered-build equal, frozen report/entry + is_tradable False +
    production_status immutable, NEVER_EMITTED tokens absent from the
    serialized body, no production imports + no random/
    uuid/datetime/scipy/sklearn, canonical e2e report_id O881c3a9a39 over
    the frozen 9N Ne4c9dc7886, validated-vs-tradable boundary render and
    emission_check). Invariants: consumes only the frozen 9N report;
    never re-simulates / re-optimizes / modifies parameters; no production
    imports; no orders/ledger; deterministic + immutable; 1:1 entries;
    the strongest statement is a VALIDATED_RESEARCH_FINDING, never a
    TRADABLE_STRATEGY. Commit: independent Phase 9O milestone -- research
    UX readback over the frozen 9N report; no
    BREAKOUT/rules/7E/production results modified.

131. **9N Research Recommendation & Evidence Readback** (autonomous,
    deterministic, research-only readback layer that turns the frozen
    9M OOS / 9L conditional-ML / 9K regime results into actionable,
    human-readable research recommendations -- completely disconnected
    from production). core/research/recommendation/: constants.py (closed
    conservative vocabulary 7E_BLOCKED / NO_EVIDENCE / INCONCLUSIVE /
    REJECTED / REQUIRES_MORE_OOS / CONDITIONAL / PROMISING /
    ROBUST_RESEARCH_FINDING, locked INVESTIGATE_FURTHER directive -- never
    a strategy change; the five READBACK_QUESTIONS; closed LIMITATIONS
    vocabulary; PRODUCTION_DIRECTIVES rejection set), ladder.py (deterministic
    total mapping of the frozen 9M final_status to the 9N vocabulary: 7E
    NO-GO always 7E_BLOCKED; a regime-scoped/conditional claim is NEVER
    promoted into a universal PROMISING / ROBUST_RESEARCH_FINDING tier;
    ROBUST_RESEARCH_FINDING requires unconditional + HIGH robustness),
    evidence.py (build_finding: recommendation -> OOS readback -> hypothesis
    readback -> optional 9L recovery/entry/calibration and 9K walk-forward/
    finding readback -> deterministic narrative answers -> limitations;
    to_recommendation flattens one finding into exactly one Recommendation
    1:1, preserving the OOS report id at the earliest point so
    recommendation.evidence_ids carries the frozen evidence reference);
    every period verdict REJECTED failure retained, nothing hidden),
    types.py (frozen Recommendation / EvidenceSummary /
    RecommendationStatistics / OosReadback / HypothesisReadback /
    AncillaryReadback / ReadbackAnswers; LIMITATIONS closed roster),
    engine.py (RecommendationEngine.run(oos_report, ml_report,
    regime_report, hypothesis_ids) -> frozen RecommendationReport; reads
    the FROZEN 9M OosReport + optional frozen 9L/9K reports; never
    simulates, never optimizes, never modifies parameters; builds
    recommendations = tuple(to_recommendation(f) for f in findings) and
    asserts len(recommendations) == len(findings)), report.py (frozen
    RecommendationReport, deterministic N+10hex report_id derived from the
    canonical payload EXCLUDING report_id -- no self-reference, no
    uuid/random/datetime/hash, stable under reordered recommendations;
    production_ready field permanently False -- construction with True
    raises ValueError and assignment raises FrozenInstanceError;
    is_production_ready property returns False; emission_check() returns a
    dict {clean, production_ready, is_production_ready,
    has_production_directive, tokens_absent, statuses_research_only,
    immutable, seven_e_blocked_preserved, never_emitted, present, reasons}
    that scans the ACTUAL serialized body; build_report(...) is the
    constructor/validator normalizing + sorting, validating statuses and
    evidence refs, rejecting production directives, forcing
    production_ready False; NEVER_EMITTED promotion tokens absent from
    the report body). Proof: tests/test_researcher_9n.py 77/77 OK (closed
    vocabulary + locked directive, ladder unit coverage over the full 9M
    ladder incl. 7E always-blocked and conditional-never-universal and
    LOW-robustness blocks top rung, evidence-chain retention + deterministic
    finding ids + frozen containers + 1:1 to_recommendation preserving the
    OOS report id in recommendation.evidence_ids, engine reading a real
    frozen 9M report (dict and object) + hypothesis filter + empty honest +
    unknown gate ValueError + 1:1 and statistics.n_recommendations ==
    len(recommendations), production guard: construction with
    production_ready=True raises, assignment raises FrozenInstanceError,
    is_production_ready property False, promotion tokens absent from the
    serialized body, no production imports + no random/
    uuid/datetime/scipy/sklearn, deterministic report id equal across
    repeat build + reordered recommendations, canonical e2e report_id
    Ne4c9dc7886 + finding N7ff6711cff mapping the 6/6 walk-forward clean
    long recovery to ROBUST_RESEARCH_FINDING, wf-false -> PROMISING,
    conditional -> CONDITIONAL, 7E -> BLOCKED). Invariants: no production
    imports; no orders/ledger; no simulation/optimization; does NOT modify
    strategy parameters; deterministic + immutable; review protocol frozen;
    every finding and limitation RETAINED; 1:1 findings == recommendations;
    research-only, never a promotion token. Commit: independent Phase 9N
    milestone -- research recommendation & evidence readback over the
    frozen 9M/9L/9K evidence; no BREAKOUT/rules/7E/production results
    modified.

127. **9J Strategy Discovery / Experiment Engine** (autonomous, deterministic,
    research-only discovery over the frozen 9A-9I layers). core/research/
    discovery/: discovery_types.py (frozen DiscoveryHypothesis/DiscoveryFinding/
    DiscoveryExperiment/StrategyDiscoveryReport + closed experiment-status
    vocabulary REJECTED/INCONCLUSIVE/PROMISING/REQUIRES_OOS/VALIDATED/BLOCKED +
    NEVER_EMITTED trio + stable_json), candidate_space.py (validate_overrides:
    draws ONLY the supported 9B ExperimentConfig axes -- an unsupported
    parameter axis or a known-but-unsupported entry model fails loudly, never
    silently invented; expiry must be a positive int; vocabulary() exposes the
    closed supported set with never_invented_axes=True), gaps.py (detect_gaps:
    deterministic gap audit by dataset source + category -- FILLED /
    ENTRY_NOT_REACHED / EMPTY / REJECTED -- with counts, settled and
    directions; recovery-first; generate_hypotheses: evidence-gated,
    executable-overrides RECOVERY_RR / RECOVERY_STOP / RECOVERY_ENTRY_OFFSET /
    RECOVERY_ENTRY_MODEL / RECOVERY_EXPIRY / RECOVERY_CONFIRMATION candidates
    carrying direction + evidence + deterministic sha1 id H+10hex; deterministic
    generation demonstrated), scheduler.py (deterministic order; explicit
    budget counting only GENERATED experiments -- INJECTED are never
    suppressed; research-memory dedup reported as skipped "previously
    studied"; invalid candidates skipped loudly and never executed),
    discovery_runner.py (StrategyDiscoveryEngine.run drives the FROZEN 9C
    CounterfactualRunner per hypothesis -> 9D ResearchAnalyzer -> 9E Research
    Intelligence -> 9F Statistical Baseline + chronological OOS fold ->
    per-experiment gates; recovered opportunities counted (count + per-category
    + added R); experiments run entirely in-memory -- persist NOTHING, never
    land a strategy), robustness_filter.py (the closed Discovery gate ladder:
    1 BLOCKED 7E-NO-GO -> 2 INCONCLUSIVE settled<10 -> 3 REJECTED no-advantage
    -> 4 REJECTED loss-expansion -> 5 REJECTED directional-contradiction (min
    5) -> 6 PROMISING economic-not-acceptable -> 7 REQUIRES_OOS -> 8 REJECTED
    OOS-did-not-confirm -> 9 PROMISING settled<30 -> 10 VALIDATED research-only,
    never production-ready; OOS can never be bypassed), baseline_comparator.py
    (economic_assessment in-sample vs OOS: capture_gain / expectancy_delta /
    loss_rate_delta / max_drawdown_delta / loss_expansion; acceptable = not
    loss_expansion AND capture_gain>=0 AND expectancy_delta>=0 AND
    loss_rate_delta<=0 AND max_drawdown_delta<=0; MAE risk_delta is REPORT-ONLY
    -- recovery-first earlier entries inherently raise avg MAE so it must not
    block VALIDATED; verdict CAPTURE_TRADE_OFF: ... or RECOVERY_CAPTURES_VALUE_
    WITHOUT_WORSE_ECONOMICS), confluence_discovery.py (observed-only 9F feature
    associations vs recovered REJECTED observations -- OBSERVED_ASSOCIATIONS_
    ONLY, never fabricated, availability list + notes). Recording: non-injected
    experiments write a 9J_DISCOVERY_COMPLETE memory row; INJECTED experiments
    are never recorded/suppressed; a second run skips generated hypotheses with
    "previously studied" and still executes injected ones. Ranking: every
    experiment retained (rejected/blocked included), deterministic id-keyed
    sort, non-increasing scores, no hiding. Proof: tests/test_researcher_9j.py
    51/51 OK (fixture geometry, candidate space incl. unsupported-axis/entry-
    model fail-loud + expiry validation, gap+hypothesis determinism/
    executability/dedup, scheduler budget/dedup/invalid-skip, closed gate
    ladder incl. OOS-never-bypassed + directional-contradiction + 7E-BLOCKED +
    small-spread-never-validated, e2e all-win->VALIDATED + 14->REQUIRES_OOS +
    6->INCONCLUSIVE + recovery 16/42-bar + SHORT-contradiction REJECTED +
    OOS-fail REJECTED/140-bar-pair + REPORT byte-identical rerun + frozen
    is_production_ready/is_production_directive + memory second-run dedup +
    observed-only confluence + empty-dataset honesty). Invariants: no
    production imports; no orders/ledger; no lookahead; deterministic;
    every experiment retained; research-only, never a promotion token.
    Commit: independent Phase 9J milestone -- autonomous strategy discovery
    over the frozen evidence; no BREAKOUT/rules/7E/production results
    modified.

133. **Phase 9P Completion Audit + Milestone 9P-a (main.py multi-symbol runtime)**.
    Removed the Phase 9P completion & production-readiness audit (9A-9O frozen
    research boundary verified; LIVE=PARTIAL/NOT_LIVE_READY, PAPER=COMPLETE,
    BACKTEST/REPLAY=COMPLETE, REAL-TIME data=INTEGRATED_BUT_NOT_VALIDATED,
    Order Flow=ORPHANED, main.py runtime=INTEGRATION GAP, control API/monitoring
    MISSING). Then implemented 9P-a: wired the CANONICAL Phase 6E multi-symbol
    RealTimeEngine into main.py's PAPER path via the new core/runtime/paper_main.py
    bridge (build_paper_engine -> RealTimeEngine -> PipelineRegistry -> PaperRuntime
    -> BrokerEngine dry-run stack; closed-candle delivery routed per-instrument by
    (exchange, instrument_id)). ExplicitSymbolUniverseManager supplies the eligible
    cut from settings.SYMBOLS (UNIVERSE="explicit", the documented fallback until
    live liquidity/history providers exist); discovery is a no-op. All collaborators
    injectable so offline tests drive the identical build path. main.py now prints
    the multi-symbol runtime header and blocks on run_paper_forever; LIVE_MODE and
    LIVE_ANALYZE-ONLY paths unchanged (legacy asyncio websocket). Proof:
    tests/test_paper_main_runtime.py 8/8 OK (explicit-universe eligible cut, blank
    filter, multi-symbol assembly + paper-only dry_run, identity routing BTC/ETH
    isolation, forming-candle never delivered, unknown-symbol unrouted, tick() one
    poll step, PaperOnlyError on live port ops). Full canonical suite
    tests/ = 1370 passed (baseline 1362 + 8); compileall clean. Commit: independent
    Phase 9P milestone -- no strategy/risk/execution/7E/production-result changes.

134. **Phase 9P-b (Account Profit Factor / Expectancy Reporting)**.
    Closed the accounting reporting gap WITHOUT a second accounting system
    and WITHOUT any strategy/execution changes. Findings: profit factor
    (Gross Profits / Gross Losses, positive vs absolute-negative completed-
    trade NET P&L) and expectancy (mean completed-trade net P&L) are
    mathematically correct at the analytics layer -- core/analytics/
    performance.py (PerformanceAnalytics / PerformanceReport, the same
    report surface the dashboard consumes) already derives them from the
    canonical completed-trade ledger (core/backtesting/trade_registry,
    status == "CLOSED", Trade.pnl = gross minus commission minus slippage
    per trade_simulator). The actual gap was (a) breakeven misclassification:
    pre-9P-b pnl == 0 was counted as a WIN; now breakeven is NEITHER a win
    NOR a loss (counted in `total`/expectancy divisor, excluded from win/
    loss counts, gross profit/loss, streaks, per-direction win rates), and
    (b) dead duplicate fields: core/risk/account_state.py declared
    profit_factor/expectancy that Account.update_statistics() never computed
    and nothing ever read -- a misleading second surface, now REMOVED (the
    account is counter-only with no per-trade outcomes; the one canonical
    calculation lives in performance.py). Deterministic edge cases: no
    completed trades -> missing-value 0.0; no losses -> +inf (documented);
    no wins -> 0.0 (no gross profit); breakeven-only -> 0.0; negative
    expectancy preserved; open positions/rejected/expired/unfilled/unrealized
    excluded; no partial-fill double count (pnl is per-trade net); costs
    honored (net pnl); reproducible idempotent report. Reports limitations
    honestly: positive expectancy / PF > 1 is NOT proof of future
    profitability; no invented missing costs -- costs follow canonical
    net-pnl semantics; R-based expectancy does not exist canonically (P&L
    mean is the definition). PerformanceReport gained a `breakeven` field;
    metrics() dict and summary() console block surface it. Proof:
    tests/test_account_profit_factor_9pb.py 13/13 OK (task fixture
    [+100,+200,-50,-100,0] -> gross_profit 300, gross_loss 150, PF 2.0,
    total 5, wins 2, losses 2, breakeven 1, net 150, expectancy 30;
    all-win inf; all-loss 0.0; breakeven-only 0.0; empty 0.0; negative
    expectancy; breakeven-not-a-win regression; open-position exclusion;
    deterministic repeat; costs honored; reconcile with booked account;
    AccountState exposes no duplicate fields; metrics() dict includes
    breakeven). Full canonical suite tests/ = 1383 passed (baseline 1370
    + 13); compileall clean. Research-layer expectancy references (9H/9K/
    9L/9M researcher, 9I readability, research_ml, 9G research intelligence,
    Phase 7/S 7E breakout asymmetry) untouched -- research-only, not account
    reporting. Commit: independent Phase 9P-b reporting milestone -- no
    strategy/risk/7E/backtest-OOS/production-result changes.

135. **Phase 9P-c (Canonical Runtime Analytics / Account Reporting Attach-Point)**.
    NOTE ON STATUS NUMBERING: this session corrects a documentation
    bookkeeping collision -- the research milestones 9H-9O already occupy
    STATUS 125-132 (9H=125, 9I=126, 9J=127, 9K=128, 9L=129, 9M=130,
    9N=131, 9O=132), so the Phase 9P milestones must CONTINUE at 133 (9P-a,
    previously miscounted as 128), 134 (9P-b, previously miscounted as
    129), and 135 (this 9P-c). The earlier 9P-a/9P-b STATUS numbers were
    renumbered 133/134 to remove the collision; the underlying work and
    commits are unchanged. Implemented 9P-c: gave the running PAPER
    runtime a deterministic, canonical way to obtain its performance
    report WITHOUT a second accounting system, WITHOUT a second PF/
    expectancy implementation, and WITHOUT restoring any account-level
    duplicate surface. Attach-points (both PURE delegation to the single
    canonical PerformanceAnalytics / PerformanceReport): (a) PaperRuntime
    .report() -> PerformanceAnalytics.analyze(account, ledger) -- the
    runtime already owned both canonical inputs (its Account + its
    TradeRegistry ledger), so this is the smallest architecture-compatible
    change; (b) RealTimeEngine.performance(symbol=None) -- per-symbol
    report for one active runtime (None for an unknown symbol, matching
    universe-routing semantics) or an aggregate PerformanceReport across
    ALL active runtimes' completed trades with a shared starting balance
    (sum of per-runtime starting balances) so final equity reconciles
    across the whole PAPER book. Data-source integrity: the report reads
    TradeRegistry CLOSED trades only; open positions, rejected/expired/
    unfilled/cancelled orders never enter the ledger (the BrokerEngine
    drops them before booking), and unrealized P&L / open positions are
    excluded by the analytics closed-only filter. Report is on-demand
    (never in the candle path -> does not block the event loop),
    deterministic for the same completed-trade state, and is the SAME
    PerformanceReport object surface the backtest / validation / dashboard
    surfaces consume. Account/AccountState remain counter-only -- the
    removed profit_factor/expectancy fields were NOT restored. No
    execution / order / risk / capital / exchange behavior changed; PAPER
    runtime and research boundaries untouched. Proof:
    tests/test_runtime_report_9pc.py 12/12 OK (runtime canonical report
    identity; completed-trade-only; open excluded; rejected/expired/
    unfilled never in ledger; breakeven neutral; PF + expectancy identity
    with canonical analytics; report updates after a close; deterministic
    repeat; account state stays counter-only; per-symbol isolation on a
    multi-symbol engine; aggregate over all symbols with shared starting
    balance; empty aggregate; deterministic aggregate). Full canonical
    suite tests/ = 1395 passed (baseline 1383 + 12); compileall clean.
    Commit: independent Phase 9P-c reporting attachment milestone -- no
    strategy/risk/7E/backtest-OOS/production-result changes.

136. **Phase 9P-d (Live Liquidity / History Provider Plumbing)**.
    Fills the ONE genuinely-missing gap in the Phase 6B universe
    architecture: real provider-backed eligibility data for the
    canonical UniverseManager. Before this phase, UniverseManager
    accepted injectable `liquidity_provider` / `history_provider`
    (duck-typed: quote_volume_24h(symbol)->float|None,
    history_bars(symbol,timeframe)->int|None) but NO real provider
    existed -- the PAPER runtime fell back to UNIVERSE="explicit"
    (settings.SYMBOLS) because, per the audit, "live liquidity/
    history providers (which do not yet exist)." Implemented ONLY
    the actually-missing plumbing (no new universe architecture, no
    second manager, no re-rewrite of MarketUniverse/UniverseManager/
    SymbolPipeline/subscriptions -- the providers FEED the existing
    cascade). (a) core/universe/liquidity_provider.py
    DeltaLiquidityProvider: fetches the REAL Delta /v2/tickers
    payload once per refresh (one REST call, not per-symbol), maps
    each symbol's `turnover_usd` (24h USD turnover -- a real Delta
    field, LIVE-VERIFIED against api.delta.exchange/v2/tickers on
    2026-09-03) to quote_volume_24h. Missing/empty/unparseable/
    zero turnover -> None -> the cascade DENIES (NO_LIQUIDITY_DATA);
    missing data is NEVER assumed liquid. Transport/fetch injectable
    for offline tests. (b) core/universe/history_provider.py
    DeltaHistoryProvider: reports the COUNT of bars available via
    the existing real DeltaHistory.candles() (LIVE-VERIFIED: BTCUSDT
    1m over 1 day -> 1440 bars on 2026-09-03), returning None on a
    failure so missing history DENIES (NO_HISTORY_DATA), never
    "assume sufficient history". (c) config/settings.py: new
    operator thresholds MIN_QUOTE_VOLUME_24H / MIN_HISTORY_BARS /
    PROVIDER_HISTORY_LOOKBACK_DAYS + UNIVERSE="provider" selector;
    an unconfigured liquidity threshold still REQUIRES a measured
    figure (gate denies None) -- a numeric bound is optional, a data
    requirement is not. (d) core/runtime/paper_main.py: new
    build_provider_universe_manager() assembling the CANONICAL
    UniverseManager + InstrumentRegistry + real providers, and
    build_paper_engine(universe_mode=...) selects the provider path
    when UNIVERSE=="provider" while PRESERVING the explicit fallback
    (default). Proof (CODE VERIFIED with mocked Delta responses,
    offline): tests/test_provider_plumbing_9pd.py 28/28 OK -- the
    critical acceptance path (REAL/NORMALIZED PROVIDER DATA ->
    canonical UniverseManager -> eligibility cascade -> ELIGIBLE
    multi-symbol set) is proven with fake providers over the real
    InstrumentRegistry/InstrumentEligibility; plus real /v2/tickers
    endpoint + turnover parsing, empty/zero/invalid turnover -> None,
    transport-failure -> None (no raise), history bar-count +
    lookback passthrough, error -> None, threshold coercion
    (invalid raises), provider policy (unconfigured -> requires_
    history False), explicit fallback default preserved, provider
    mode builds canonical manager with injected fakes. LIVE EXCHANGE
    VERIFIED (separate from code verification, documented here):
    /v2/tickers turnover_usd present for liquid symbols, empty for
    inactive; /v2/history/candles counted. Async/network safety:
    providers run in the SAME synchronous cadence-based universe
    refresh path as the existing product discovery (RefreshScheduler
    -> manager.build_universe), NOT in the real-time candle delivery
    path -- no blocking HTTP added to the live event loop. Full
    canonical suite tests/ = 1423 passed (baseline 1395 + 28);
    compileall clean; no strategy/risk/7E/backtest-OOS/execution/
    capital/research changes. Commit: independent Phase 9P-d
    provider-plumbing milestone.
137. **Phase 9P-e (Provider-Universe Live Smoke / Verification Harness)**.
    Reproducible, read-only/PAPER-only live-exchange smoke harness for
    the Phase 9P-d provider-universe path (real Delta data -> canonical
    6B eligible universe -> subscriptions -> PAPER runtime), with safe
    bounded shutdown and a structured report. (a)
    core/runtime/provider_universe_smoke.py: ProviderUniverseSmoke +
    ProviderUniverseSmokeReport + error category constants
    (NETWORK_UNAVAILABLE / API_ERROR / PARSE_ERROR / NO_INSTRUMENTS /
    NO_LIQUIDITY_DATA / NO_HISTORY_DATA / NO_ELIGIBLE_INSTRUMENTS /
    RUNTIME_INITIALIZATION_FAILURE) + classify_reason() + CLI entry
    `python -m core.runtime.provider_universe_smoke`. Reuses ONLY the
    canonical UniverseManager / InstrumentRegistry / eligibility
    cascade / SymbolPipeline / subscriptions / PaperRuntime / the single
    liquidity+history provider architecture + build_paper_engine
    (UNIVERSE="provider"); provider-selection is always `provider`,
    never accidental `explicit`; mode-selection requires a provider
    (builder forces provider mode; fails closed otherwise). The harness
    primes DeltaLiquidityProvider.refresh() before each build_universe()
    (quote_volume_24h reads the snapshot map), surfaces RefreshScheduler
    discovery errors into report.errors (NetworkUnavailable -> NETWORK,
    else API), distinguishes DATA_UNAVAILABLE (liquidity/history) from
    ELIGIBILITY_REJECTED, defaults bounded/terminating (no hanging
    WebSocket: engine.stop() closes transport + sets stop event; pump
    loop is daemon and breaks on stop). Bounded CLI adds --symbols /
    --passes (default 2, so a FRESH registry graduates NEWLY_LISTED ->
    ACTIVE via the Phase 6A confirmation state machine) / --min-volume /
    --min-bars overrides; discovery is filtered to the chosen symbols
    in-memory (one real /v2/products call, no per-symbol REST
    explosion; history remains per-symbol as required). (b)
    tests/test_provider_universe_smoke_9pe.py: 17/17 offline tests
    (mock transport/fakes over real cascade) covering mode provider
    required/selected, real-provider construction, live-data success
    (eligible cut -> 3 runtimes/pipelines/subscriptions), network/API/
    history failure classification, empty eligible universe reported
    (exit 3), classify_reason, PAPER-only guard (LIVE_MODE without
    PAPER_MODE refuses), clean shutdown (WS closed, no dangling
    workers), structured deterministic report, fresh-registry
    confirmation (1 pass -> 0 eligible NOT_CONFIRMED; 2 passes ->
    graduated eligible), and LOW_LIQUIDITY rejected cut vs AVAILABLE
    bucket separation. LIVE EXCHANGE VERIFIED on 2026-09-03 against
    real api.delta.exchange REST + WebSocket: (i) default 1m, 3 symbols
    (BTCUSDT/ETHUSDT/SOLUSDT): 3/3 ELIGIBLE -> 3 runtimes, 3
    pipelines, 3 subscribed, paper_only=true, clean ~13s bounded exit,
    no errors; (ii) --min-volume 5000000 --min-bars 1000: 0 eligible,
    ALL LOW_LIQUIDITY from REAL turnover (BTCUSDT ~3.1M, ETHUSDT
    ~4.2M, SOLUSDT ~118K, DOGEUSDT ~1.3K USD 24h) -- the harness did
    NOT weaken thresholds to manufacture an eligible cut, and kept
    DATA AVAILABLE distinct from ELIGIBILITY REJECTED; (iii)
    --min-volume 100000 --min-bars 300: mixed cut BTCUSDT/ETHUSDT/
    SOLUSDT ELIGIBLE (3 runtimes/pipelines/subscribed) vs DOGEUSDT
    LOW_LIQUIDITY (real sub-100K turnover) -- acceptance chain proven
    live with real rejection reasons and clean shutdown. Runtime
    Safety: PAPER-only (paper_only=true), LIVE_MODE-without-PAPER guard
    + bounded CLI; no live orders, no weakening of eligibility; empty
    (0 eligible) universe reported as such (exit 3), not manufactured
    as success. Full canonical suite tests/ = 1440 passed (baseline
    1423 + 17); compileall clean; tracked .pyc restored; no strategy/
    risk/7E/backtest-OOS/execution/capital/research changes. Commit:
    independent Phase 9P-e provider-universe live smoke / verification
    milestone.


138. **Phase 9P-f (Paper Control & Monitoring API)**.
    Read-only-first Control & Monitoring HTTP API + a safe PAPER-only
    control seam over the canonical RealTimeEngine, enforcing
    API -> Command/Query -> Existing Runtime (the engine stays the
    single source of truth; the API adds no strategy/risk/order/live
    logic). stdlib-only (no new dependency). (a)
    core/runtime/lifecycle.py: EngineLifecycle -- thin control manager
    owning a daemon control poll thread + RLock-serialized state model
    (STOPPED/STARTING/RUNNING/STOPPING/FAILED) + commands allowlist
    {start, stop, restart, emergency_stop}; emergency_stop is a
    highest-priority local PAPER shutdown, strictly idempotent (2nd call
    = zero duplicate shutdown work, no error, stays STOPPED); start
    failure -> FAILED (recoverable); bounded joins (no indefinite HTTP
    blocking). (b) core/monitoring/api_server.py -- stdlib
    ThreadingHTTPServer hard-bound to 127.0.0.1, bearer-token
    constant-time hmac.compare_digest auth, fail-closed when tokenless,
    GET read endpoints /health /universe /subscriptions /runtimes
    /market /signals /positions /orders /account /risk /performance
    /errors (delegate to existing statuses()/performance()/
    portfolio.snapshot()/runtime.state()/subscriptions), POST /control
    with _assert_paper_capable (refuses LIVE-mode or any non-dry_run
    runtime); no GET mutates state; API never calls poll() directly. (c)
    core/monitoring/service.py (enabled/config_token/start_api/fail-
    closed ControlApiConfigError), config/settings.py knobs
    CONTROL_API_ENABLED/TOKEN/HOST/PORT/POLL_SECONDS. (d) Runtime Safety:
    PAPER-only (refuses non-dry_run), token + localhost, fail-closed,
    no determinism/lifecycle change to engines, no live/order path; no
    certificate/TLS code anywhere in repo and 9P-f does no outbound TLS,
    so the host cert error has no 9P-f source; no verify=False/CERT_NONE
    workarounds added. Tests tests/test_lifecycle_9pf.py (19),
    test_api_server_9pf.py (19), test_monitoring_service_9pf.py (3) = 48
    passed over the real ThreadingHTTPServer on 127.0.0.1 ephemeral port.
    Full canonical suite tests/ = 1488 passed (baseline 1440 + 48);
    compileall clean; git diff --check clean; tracked .pyc restored;
    no strategy/risk/7E/backtest-OOS/execution/capital/research changes.
    Commit: independent Phase 9P-f paper control and monitoring API
    milestone (04739eb).

139. **Phase 9P-g (Production PAPER Entrypoint Integration)**.
    Very narrow runtime-entrypoint integration wiring core/monitoring/
    service into the production application so there is ONE coherent
    startup model: main.py -> PAPER application -> (Control API |
    EngineLifecycle -> RealTimeEngine -> PaperRuntime). (a)
    core/runtime/lifecycle.py: EngineLifecycle.wait([timeout]) blocking
    seam (returns current state; releases when the lifecycle leaves a
    running state) via a _stopped_event wired into start() (cleared) /
    stop()/emergency_stop()/start-failure (set). (b) core/monitoring/
    service.py: _active_server duplicate-server guard (refuses a second
    start while one is running), stop_api(server), and the production
    entrypoint helpers start_paper_service() -> (lifecycle, server),
    block_until_stopped() (waits then shuts down BOTH lifecycle and
    server), run_paper_with_monitoring() (drive engine via
    EngineLifecycle + gated API + block + clean shutdown). (c) main.py:
    the PAPER path now calls run_paper_with_monitoring(engine) in place
    of the blocking run_paper_forever(engine) (removed the explicit
    engine.refresh(), since lifecycle.start() -> engine.start() ->
    refresh()); the API is ENABLED ONLY when explicitly
    CONTROL_API_ENABLED=true + token, so the disabled default preserves
    the pre-9P-g behaviour exactly; run_paper_forever left in place for
    direct-loop callers. (d) Runtime Safety: localhost + bearer token +
    PAPER-only preserved; no live API, no mobile UI, no strategy/risk/
    order API; the API and PAPER runtime share the SAME authoritative
    engine; shutdown stops both cleanly. Tests: tests/test_paper_
    entrypoint_9pg.py (4) drives the real acceptance path offline (real
    build_paper_engine with fakes + real HTTP server -> GET /health /
    /universe /performance -> POST /control/stop -> blocker drains,
    server+lifecycle+engine all stopped), plus API-disabled-default
    (lifecycle runs, NO HTTP server); test_monitoring_service_9pf.py
    grows a duplicate-server-refused + start_paper_service +
    block_until_stopped clean-shutdown tests; test_lifecycle_9pf.py
    grows 4 wait() tests. Full canonical suite tests/ = 1498 passed
    (baseline 1488 + 10); compileall clean; git diff --check clean;
    tracked .pyc restored; no strategy/risk/7E/live order changes.
    Commit: independent Phase 9P-g production PAPER entrypoint
    integration milestone.


140. **Phase 9P-h (Lightweight Desktop Control Client)**.
    A thin, read-only-first Tkinter/ttk desktop control & monitoring
    terminal over the existing Control API (9P-f/9P-g). The UI is a
    renderer/controller only: it consumes GET reads and issues the
    four allowlisted POST /control lifecycle commands -- it NEVER
    imports engine internals, recomputes strategy/risk/position/
    order/performance, constructs orders, or touches an exchange.
    (a) core/client/ package, launched `python -m core.client.app`
    (or `python -m core.client`), stdlib-only, zero new dependencies:
    tkinter/ttk + urllib.request + json + threading + queue + time.
    Modules: config.py (host/port/token/poll, defaults 127.0.0.1:8787,
    token from QENGINE_CLIENT_TOKEN/CONTROL_API_TOKEN env, never
    hardcoded, as_dict() never exposes token), http_client.py
    (ApiClient GET/POST with bearer auth via urllib, timeouts, and
    typed errors: Authentication/Connection/Timeout/Server/
    BadResponse/ControlRejected; ReconnectingClient tracks connected/
    disconnected), poller.py (single daemon background worker, one
    coordinated read cycle per interval with a no-overlap guard,
    per-endpoint error isolation, clean stop via Event, results to a
    thread-safe queue), controller.py (pure display logic mapping
    CycleResult snapshots to rows; only POST is the ControlPath
    verbs start/stop/restart/emergency_stop against the real
    /control {"command": ...} contract), app.py (DesktopClient:
    header connection/engine status, Dashboard/Universe/Market/
    Trading(Signals,Positions,Orders,Account,Risk)/Performance/Logs
    tabs, control bar with confirmations incl. a stronger Emergency
    Stop confirmation, background poll -> queue -> root.after()
    drain so HTTP never runs on the Tkinter thread, and DISCONNECTED
    -> CONNECTED auto-reconnect with no engine restart). (b)
    Engine isolation verified: client imports only stdlib + its own
    core.client modules (grep-confirmed: no core.runtime/engine/
    strategy/risk/execution/exchanges/pipeline, no TradeRegistry/
    BrokerEngine/RealTimeEngine). No secrets in source; token only in
    the Authorization header, never logged/displayed/in URLs. No new
    dependency (requirements.txt unchanged). No invented API endpoints
    (consumes exactly the 9P-f GETs + POST /control). Closing the UI
    stops ONLY the poller -- it never stops the engine. (c) Tests:
    tests/test_client_9ph.py (25, stdlib-only, in-process fake
    http.server Control API -- no network): HTTP client GET/POST/
    bearer-header/timeout/401/500/malformed-JSON/unreachable; control
    allows-exact /control+command body; ReconnectingClient connected/
    disconnected; config defaults/custom/from_env/no-token-in-as_dict;
    poller results-reach-queue / connection-failure-no-crash / clean
    stop; controller dashboard/universe/empty-universe/performance-
    report/positions/errors-"no-secret" rendering. (d) Offline runtime
    smoke verified (fake-engine + REAL Control API + REAL ApiClient/
    Poller): health RUNNING, universe BTCUSDT/ETHUSDT, performance
    rows, POST /control stop -> lifecycle STOPPED + engine.started
    False -- client connects to the real 9P-f contract end-to-end
    without network. Full canonical suite tests/ = 1523 passed
    (baseline 1498 + 25); compileall clean (full `compileall .`);
    git diff --check clean; tracked .pyc restored; no strategy/risk/
    execution/exchange changes. Known limitations: presentation-only
    (no charting/advanced analytics/order-entry/live/credential
    management -- explicitly out of 9P-h scope); tkinter window needs
    a display (logic is display-free and headlessly tested); single
    default universe view; no mobile/web client yet (they can later
    consume the SAME API). Commit: independent Phase 9P-h lightweight
    desktop control client milestone.

141. **Phase 9P-i (Integration & Operational Hardening / Runbook)**.
    A no-new-feature phase that proves and documents the complete
    existing PAPER stack: fresh env -> engine -> Control API ->
    desktop client -. It re-verified the canonical runtime path
    (main.py -> paper_main.build_paper_engine -> RealTimeEngine ->
    PipelineRegistry -> PaperRuntime -> BrokerEngine dry_run), the
    Control API (disabled-by-default, localhost-bound, constant-time
    bearer auth, fail-closed without a token, read-only except the
    four allowlisted PAPER lifecycle verbs), the EngineLifecycle state
    model (STOPPED/STARTING/RUNNING/STOPPING/FAILED with idempotent
    start/stop and strictly-idempotent emergency_stop), PAPER-only
    safety (no live-order path; the API asserts paper-capable before
    control), the provider universe cascade (missing/zero data DENIES,
    never fabricated eligible), and the Delta data layer (best-effort,
    exponential-backoff reconnection, empty universe is a valid state).
    (a) Fixed a real hardening defect found by `python -m compileall .`:
    `core/client/app.py` module docstring had an invalid escape
    sequence `\ ` that emitted a SyntaxWarning on import/compile;
    re-drew the ASCII art with ``- `` so the package compiles warning-
    free. (b) New offline, committed end-to-end integration tests
    tests/test_integration_9pi.py (10 green): the REAL core.client
    package (ApiClient/Poller/ReconnectingClient/ControlPath/controller
    renders) drives the REAL Control API + REAL EngineLifecycle + a
    canonical fake PAPER engine over localhost -- no network, no
    credentials. Covers the full loop: real client reads authoritative
    health/universe/runtimes/performance; the poller produces a
    coordinated CycleResult; the controller renders real server data
    verbatim (never recomputes); the four lifecycle verbs work end-to-
    end THROUGH the real client; the ReconnectingClient probes; a NEW
    TEST proving the client tears down WITHOUT stopping the engine
    (only an explicit lifecycle stop does); fail-closed (API enabled
    without token refuses to start) and disabled-runs-lifecycle-without-
    HTTP are re-confirmed; and a secret-handling regression proving the
    bearer token never appears in ANY API response body or error string.
    (c) New tests/test_client_isolation_9pi.py (2 green): a committed
    import-isolation regression that runs a FRESH-interpreter subprocess
    importing every core/client module and asserts the resulting core.*
    import set is ONLY core/client (plus the stdlib support boundary) --
    never runtime/live/risk/execution/exchanges/pipeline/research/
    backtesting/analytics/registry/universe/etc. and no engine objects
    (TradeRegistry/BrokerEngine/RealTimeEngine/PipelineContext/...) --
    so a client->engine import cannot silently reappear. Direct audit
    also confirmed: no hardcoded secrets in source (keys/token are env
    -only, never logged, never in URLs or reports). (d) Docs:
    docs/RUNBOOK.md (new, complete operational run guide: env setup,
    install, exact env-var configuration for PAPER local / PAPER+Delta /
    Control API / client, start engine, enable API, start client,
    verify, safe shutdown, emergency stop, reconnection, a
    troubleshooting table, security notes, localhost-only multi-machine
    note, and a full verification checklist). STATUS.md entry 141;
    project_manifest.md + import_manifest.md updated. Full canonical
    suite tests/ = 1535 passed (1523 baseline + 12 new); compileall
    clean (and now warning-free); git diff --check clean; tracked .pyc
    restored; requirements.txt unchanged (zero new runtime deps). Each
    test independent/offline/deterministic; no reliance on Delta,
    Internet, credentials, or a Tk display. Commit: independent Phase
    9P-i integration & operational hardening / runbook milestone.


142. **Phase 9Q (Core Correctness 12/12) + 9R/9S (Research Integrity + Market Hardening)**.
    9Q-1 baseline (1568 tests, 24 archive collection errors documented), 9Q-2 Wilder ATR (replaced SMA sum/period with Wilder RMA TR=max(high-low,abs(high-prev_close),abs(low-prev_close)), seed SMA, ATR_t=((ATR_{t-1}*(N-1))+TR_t)/N, batch==incremental, 12 tests), 9Q-3 causal per-bar ATR (DisplacementScanner now uses ATR_series[N] not latest, future-mutation test 3/3, pipeline count preserved via tr_multiple=0 warmup), 9Q-4 canonical financial accounting (core/backtesting/accounting.py with gross_pnl, 
et_pnl, 
otional, position_return_percent, portfolio_return_percent, 
ealized_r, classify_pnl), 9Q-5 breakeven (AccountState.breakeven_trades, ook_breakeven, pnl>0 WIN, <0 LOSS, ==0 BREAKEVEN, 16 tests), 9Q-6 canonical timestamp (core/common/timestamp.py UTC seconds, seconds/ms/µs/ns, 14 tests, adapters normalize at boundary), 9Q-7 CandleBuilder 	hreading.RLock (current/history/series, load_history atomic, 8 tests), 9Q-8 risk contract (docs/audit/risk_config_contract.md), 9Q-9 position sizing explicit (PositionSize requested vs actual, capped/cap_reason, 	ests/test_position_sizing_9q.py 7/7), 9Q-11 intrabar (Trade.ambiguous, conservative SL-first, 6 tests), 9Q-12 settings type safety (_env_float/_env_int fail-fast, 12 tests), 9R-1 walk-forward disjoint (	est=start..start+step not start..n, purge/embargo, 7 tests), 9R-5 Sharpe on position return (pnl/notional), 9R-6 reproducibility (	ests/test_reproducibility_9r.py 4/4), 9S parity/realism (	ests/test_parity_9s.py 4/4, 	ests/test_baseline_9s.py 2/2). Full suite **1683 passed** (was 1568, +115 new), compileall clean, **9P-k 28/28 still green**. Commits: 060da3d, 6aec29f, 45eb621, d4d03ec, 8e00d19, 279fe51, cc32b31, b7f3173, ae40260, 130ac36, 7a7d2f4, 21797ff, eea4a85. 9Q **EXIT-GATED**, 9R/9S audited. No AI Confluence, no NSE, no live enablement per §33-35. Historical results invalidated until fresh baseline (§36).



143. **Phase 9R/9S (Research Integrity + Market Hardening — Build Continuation)**.
    9R-1 walk-forward disjoint with purge_bars/embargo_bars (AFML 7.4); 9R-2 feature timestamp audit via CausalWindow; 9R-5 Sharpe on position return pnl/notional; 9R-6 reproducibility; 9S REST 429 Retry-After + backoff; 9S market hardening. Full suite **1698 passed** (was 1683, +15). Commits: 3874f72. (Entry text condensed 2026-09-10: original contained control characters; substance preserved.)


144. **Stage 1-3 Production Hardening Closure + Stage 4 Paper Certification**.
    Stage 1-3 (closure fad7329): authoritative MIN_RISK_REWARD=6.0 (decision gate + risk revalidation), central CostSpec (explicit-zero defaults; research ladders untouched), fail-closed Reconciler (startup/runtime halt, atomic journal, gate-first arming), portfolio fail-closed numerics, bounded swing cache (5000), WS heartbeat classification + pump backoff, PARTIAL!=FILLED pins. Full suite 2610 passed at closure.
    Stage 4 (this entry): paper certification on the ACTUAL pipeline — paper-only CostSpec profile (PAPER_* settings, env-overridable, explicit-zero-neutral, CONFIGURATION_REQUIRED for venue claims), kill-switch seam in RiskEngine (kill_switch/trading_enabled/QE_KILL_SWITCH, mandatory path), realized-RR stamp (OrderIntent.actual_risk_reward at NEXT_BAR_OPEN fills; fill erosion measured, order-time gate GREEN), 30k-candle soak (192 trades, net -10.45 REPORTED not optimized, violations=[], cache bound holds), 10k double-run byte-identical, causality green, 12 crash drills safe, WS storm green, GAP_REPAIR=NOT_IMPLEMENTED documented, multi-symbol isolation green, zero exchange writes (paper/research/AI, call-counted). Full suite 2742 passed / 0 failed; compileall clean. SECURITY BLOCKED (history exposure, operator action pending). Research byte-unchanged (freeze f803fe7d, D3 sealed). NO EDGE ESTABLISHED. OOS ABSENT. LIVE NO-GO. PAPER CONDITIONAL. See docs/stage4_paper_certification.md.


145. **Phase 12 (Critical Safety, Execution Correctness, Data Durability & Recertification)**.
    NOT a strategy phase: no threshold tuned, no hypothesis rescued, no edge claimed, LIVE stays NO-GO, is_production_ready stays False, no orders placed, no credentials rotated. Corrects the forensic P0/P1 defects, then recertifies.
    P0 -- ack-before-filled (core/execution/order_ack.py NEW: AckResult + classify_ack/classify_exception, fail-closed UNKNOWN/PARTIAL; core/live/broker_engine.py live route classifies every ack -- FILLED only on fill evidence, PARTIAL/UNKNOWN halt via reconciler, dead states clear without halting; fill confirmation on position sighting / fetch-confirmed fill; _ack_state/_fill_confirmed/_last_error; journal persists ack_state + order_seq; tests/test_execution_ack_12.py 23 tests incl. zero/partial/complete/rejected/cancelled/expired/lost/dup/delayed ack, executor-exception cleanup, kill-blocked routing, deterministic client ids). P0 -- executor exceptions clear transient state + halt (same seam + tests). P0 -- historical .env in 4 pre-hygiene commits documented COMPROMISED (operator must rotate; no purge without authorization); .env untracked + .env.example keys-only verified; logs/engine.log removed from tracking (file preserved, ignored); tests/test_security_12.py 6 tests (tracking, banner secret-free, LIVE defaults, conflict fail-closed). P1 -- kill switch now covers pending fills (backtester), legacy fills, live routing (broker dry+live), paper fills (existing state stays observable; tests/test_risk_gates_12.py 25 tests). P1 -- loss limits WIRED (Option A): AccountState UTC day/ISO-week/month keys + roll_pnl_windows(), RiskEngine loss_limit_blocked() (exact equality blocks, non-finite blocks fail-closed); MAX_OPEN_POSITIONS documented as structurally enforced (single slot) + pinned test. P1 -- legacy same-candle path = test-harness behavior, now explicitly gated (kill + geometry + RR); P1 -- inverted stops rejected via accounting.directional_geometry_ok()/order_rr() (builder + RiskEngine + legacy gate); P1 -- NEXT_BAR_OPEN fills revalidate actual RR >= 6 BEFORE mutation (eroded fills refused, setup untouched; stops/targets never moved). P1 -- confirmed_bar stamp (index + right) + confirmed_as_of() embargo (emission already guaranteed it; now explicit) + tests/test_confirmed_bar_12.py 9 tests (stamping, horizon, embargo, swing/BOS/FVG/pipeline future-mutation invariance). Market data: load_history normalizes timestamps (ms == s); paginated acquisition decrements by NEW candles (sparse under-fetch fixed); stream gap_status() (CONTINUOUS vs DATA_GAP_UNREPAIRED) + deterministic repair_gaps() via injectable fetcher (never fabricated/merged) + lazy gap state for bare transports; legacy websocket_client classified LEGACY/DEPRECATED; router eviction proven safe by watermark (prior audit claim of re-admission disproven); tests/test_market_data_12.py 8 tests. Deterministic client order ids (registry order_id sanitized; monotonic fallback; snapshot-persisted seq). Memory: dispatcher explicit maxlen + drop counter; cache retention documented + pinned; extended soak green + deterministic; tests/test_memory_bounds_12.py 4 tests. Reconciler journal gains ack_state + order_seq (schema v1 additive; RAM-truth + 30-bar cadence classified as limitation). Economic honesty: PerformanceReport gains total_modeled_costs + cost_basis ("gross theoretical" vs "friction-adjusted"; never executable/OOS/live). Docs: project/import manifests updated (incl. secrets.py phantom REMOVED, orphan/research-only classification for orderflow/volume/Wyckoff/Fib/confluence, no 11H-11U -- Phase 11G sub-phases A-U terminology); requirements drop loguru (zero importers; orphan core/logger.py quarantined to _archive/); 5 demo test files guarded for side-effect-free collection (pipeline_runner network-at-import fixed); 30 zero-test files DOCUMENTED AS EXAMPLE centrally (no deletes; test_pipeline_regressions is shared fixture + real tests).
    RESEARCH FREEZE SUPERSESSION (disclosed, precedent: 11G-Q allowlist edits): the 8 research guard tests (11g_n..u tree/isolation) now enforce the RESEARCH freeze (research/ + docs/audit/ frozen) instead of a whole-tree freeze; research/ byte-unchanged, verdicts stand (L no-edge, M NO-GO, Q-U data-insufficient).
    BASELINE ECONOMICS CHANGE (mechanism, not tuning): Gate A frozen snapshot now 25 orders / 2 fills / 0W / 2L / net -0.206452 (was 27/11/6W/5L/+3.81): 21 ORDER_SKIPPED_RR_EROSION refusals + 2 geometry-gated creations. The production BREAKOUT default is nearly unfillable under its own 6:1 invariant on observed data -- a STRATEGY viability finding, reported not fixed. Soak seed 42->6 (fixture choice; 30k invariants green; economics reported not asserted). Scripted-test fixtures corrected to 1:6-compliant geometry wherever the mandated gates apply (hardening/contract/breakout/position/optimizer/portfolio/walk-forward/research-journal/cert/soak suites -- mechanics assertions unchanged in strength + new negative tests prove sub-6:1 injected orders never fill).
    H2 (async scheduler wiring) + H3 (live equity sync) remain UNVERIFIED/deferred (operational enhancements, out of P0/P1 scope). Full suite recertified green (see commit); compileall clean; diff-check clean. EDGE = NOT ESTABLISHED. OOS = ABSENT. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED (history purge + rotation remain operator decisions).


146. **Phase 13 (Independent Recertification, Strategy Viability & True OOS Readiness)**.
    RESEARCH/RECERTIFICATION: frozen strategy untouched, 1:6 invariant untouched, no tuning, no promotion, no live. Independently reproduced Phase-12 baseline (HEAD c145f06; 2836 collected at the time; Gate-A 25/2/-0.21 PASS byte-identical).
    EROSION DECOMPOSITION (Gate-A frozen snapshot, recalculated from execution records): 3687 setup events -> 25 orders (15 EXPIRED / 8 INVALIDATED / 2 FILLED, actual 7.44 + 7.911). Refused: 22 triggered (21 ENTRY_GAP erosion + 1 compliant-but-single-position-blocked sibling) + 1 never-triggered. Pre-fill RR >= 6 on 25/25 (median 44.2); actual-fill median 0.332, erosion median 43.97 (worst 350.73); adverse gaps median 273 pts, ZERO favorable-gap refusals; fees/slippage erosion exactly 0.0 (zero-cost config). Worst case hand-verified against order_rr (351.0 -> 0.2685 exact).
    EXECUTION-MODEL FIX (one genuine Phase-12 regression found): unsigned-only erosion check admitted gap-THROUGH-target fills; directional_geometry_ok() now runs FIRST at execution time (ORDER_SKIPPED_INVERTED_FILL). Gap-through-stop was already unreachable (any such bar breaches first -> INVALIDATED, proven). 8-cell gap matrix (LONG/SHORT x above-target/below-stop/between/boundary) refused-or-invalidated, no phantom fills; simulator sign-adversarial tests (incl. SL-first ambiguity both directions) green; Gate-A re-ran IDENTICAL after the fix. Paper legacy fallback (pre-risk execution_signal) given the same kill+geometry+RR gate (legacy example path, now consistent).
    VIABILITY OUTCOME B -- LOW EXECUTABLE OPPORTUNITY (not a defect): 2 fills/5000 bars (~1 per 2500 bars); post-trigger actual>=6 on 2/24 (8.3%); median actual-fill RR 0.332. Engine correct; strategy nearly unfillable under its own constraint. No RR lowering, no stop/target/threshold/filter changes made or proposed. STOP after reporting.
    P0/P1 RECERTIFIED (all Phase-12 claims VERIFIED from source + green suites): ack truth, exception safety, security posture, kill coverage (creation+pending+legacy+paper+live-route; all open_trade production callers enumerated+gated), loss limits (boundaries/NaN/roll), max positions (structural), legacy isolation, geometry, actual-fill RR. Market data PARTIAL (itemized; no upgrade). Reconciliation PARTIAL (exchange-authoritative reads; RAM working state; ~30-bar cadence; halt-not-persisted; no indefinite-RAM endorsement). H2/H3 DEFERRED WITH JUSTIFICATION (perf-only; never-armed-live-path). Research intact (research/+docs/audit/ byte-unchanged; H004/H007 FAIL; 11G-Q gate file + 6,175-bar threshold preserved). Connectivity: 19 engines, orphans stay orphaned (confluence/price-ladder zero production importers; Wyckoff/Fib comment-only in prod). Microstructure truth: OHLCV-only candles; FOOTPRINT/DELTA/CVD/L2 = UNAVAILABLE. Economics: zero-cost defaults labeled gross-theoretical; spread unmodeled; funding absent; min-notional absent (fidelity gaps stated). OOS: infrastructure AVAILABLE, evidence ABSENT (7E rejected; no multi-period OOS). N=2 fills reported as data, never evidence.
    TEST INTEGRITY (§31): 40 test files audited -- 8 NEW strict files + 3 added classes; ~20 VALID CORRECTION fixture migrations (mechanics preserved, several assertions ADDED); REQUIRED UPDATE pins (Gate-A baseline, cert/soak seeds with rationale, freeze-guard re-scope with research freeze preserved, demo import guards); WEAKENING none; QUESTIONABLE none.
    TESTS: pytest 2849 collected / 2849 passed / 0 failed (per-file reconciled against collection; +13 vs Phase-12 = lookahead 3 + simulator-sign 5 + SHORT-gap 3 + LONG-gap 2, all new Phase-13 tests); unittest discover UNTESTED/TIMEOUT (>10 min cap, pre-existing); unittest samples green (29/29 new); compileall clean (scoped AND full `.`). Determinism (identical double-runs; 3-boundary x 3-future lookahead byte-identical pre-T), isolation (FORBIDDEN-token + mock guards), security (env-refs only) all green. EDGE = NOT ESTABLISHED. OOS = ABSENT. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False. (See docs/phase13_independent_recertification.md.)
147. **Phase 14 (Executable Edge Forensics & Economic Truth Audit)**.
    FORENSICS ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-13 baseline from source (HEAD af55a7d; Gate-A 25/2/0W/2L/-0.206452 PASS byte-identical; 2849 stable collection).
    BAR-MAPPING CORRECTION (material): Phase-13 erosion analysis read entry-bar opens one bar late (backtester bar = list_index + 1; proven by recorded trade entries + stamp==recalc agreement on both fills). Corrected Gate-A numbers: fills actual 12.1875 + 7.911 (BOTH opened exactly at E -- zero gap); actual-fill median 0.273 (was 0.332), erosion median 44.01 (was 43.97), adverse-gap median 280.2 (was 273), smallest-adverse-gap refusal 75 pts (was 40). Phase-13 doc/STATUS-146 retain the superseded figures as history; the corrected record is research/results/phase14_executable_edge_forensics.json + this entry. Conclusion unchanged (outcome B), mechanism sharpened: ONLY zero-gap opens survive.
    LIFECYCLE IDENTITY (mandatory): terminal states EXPIRED/INVALIDATED/FILLED are mutually exclusive per order (single status field, PENDING-only transitions): 25 = 15 + 8 + 2. Refusals are fill-attempt EVENTS (21 erosion + 0 inverted in Gate-A), never terminal states -- summing them double-counts. Full 25-order forensic table in the artifact (no filtering, no top-N).
    P0/P1 RECERTIFIED (all VERIFIED from source + green suites); market data PARTIAL; reconciliation PARTIAL; H2/H3 DEFERRED WITH JUSTIFICATION (perf-only; never-armed-live-path). Research intact (research/+docs/audit/ byte-unchanged; 11G-Q gate + 6,175-bar threshold preserved). Connectivity unchanged (19 engines; orphans orphaned). Microstructure: OHLCV-only; FOOTPRINT/DELTA/CVD/L2 UNAVAILABLE. Costs: structural VERIFIED-zero; fee/slippage scenarios ASSUMED (2.5bp/1bp illustrative, NOT venue-verified); funding UNAVAILABLE (zero NOT substituted).
    VIABILITY: 3687 setup events -> 24 triggers -> 25 orders -> 2 fills (8% of orders; 0.04/100 bars); N=2 reported as data, never evidence. DIRECTIONAL ASYMMETRY noted descriptively (13 BEARISH/0 fills vs 12 BULLISH/2 fills, N tiny, no inference). REGIME UNAVAILABLE at order level (none invented).
    TESTS: pytest 2849/2849/0 (reconciled; includes new test_edge_forensics_14.py 22: funnel exclusivity, phantom-win classification, single-multiplication, funding absence, cost scenarios, gap boundaries, OOS/gate pins, posture); unittest discover TIMEOUT (honestly reported, canonical runner is pytest); compileall clean (scoped + full). Determinism: artifact regenerated byte-identical (sha256 30f633fd...). No parallel paths (worker-invariance N/A, stated). NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY.
    EDGE = NOT ESTABLISHED. EXECUTABILITY = LOW_EXECUTABLE_OPPORTUNITY. OOS: infrastructure AVAILABLE, evidence ABSENT. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED (operator action). PRODUCTION_READY = False.
148. **Phase 15 (Real-Market Evidence Readiness & Genuine OOS Validation)**.
    FORENSICS/READINESS ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-14 baseline from source (HEAD 2ca80ae; Gate-A 25/2/0W/2L/-0.206452 PASS byte-identical; pytest 2904 collected = 2849 + 22 edge-forensics + 33 researcher-15, all green with per-file reconciliation).
    DATA READINESS: Gate-A dataset BTCUSDT 1m x5000 over 3.47d (Delta /v2/history/candles per acquisition record; rows carry no venue tag); continuity VERIFIED (5000/5000 60s steps, zero dupes, normalized) but 92.6% flat / 85.3% zero-volume minutes of unknown provenance (quiescence vs feed artifact indistinguishable from OHLCV) -- venue DIRECT_TARGET_VENUE-by-record with caveat; instrument schema VERIFIED, population PARTIAL (no min-notional anywhere); fees explicit-zero VERIFIED, no machine fee schedule (ASSUMED-only); funding UNAVAILABLE (zero NOT substituted); microstructure UNAVAILABLE (OHLCV-only; no trades/depth/funding endpoints in adapters); network TCP to api.delta.exchange OK but only candles/products endpoints exist -- trades/funding/L2 have no adapter.
    EXECUTABILITY (frozen): 3687 setups -> 24 triggers -> 25 orders -> 2 fills (0.04/100 bars; trigger/order/fill/completion/RR-reject/starvation rates recorded); BEARISH 13/0 fills vs BULLISH 12/2 fills (descriptive asymmetry, N tiny); REGIME UNAVAILABLE at order level (heuristic trend/range only, no VOL labels, none invented); single symbol (nothing removed/promoted).
    OOS: infrastructure AVAILABLE (deterministic chronological splitter, no overlap/shuffle, purge/embargo params, 6-period/30-opp/10-trade/60-total/5-of-6 protocol frozen; Sidak+Holm guards preserved); evidence ABSENT (periods [] -- 3 adequate periods need ~75k+ fresh bars at ~1 fill/2500 bars; 11G-Q 6,175-bar gate intact and unmet; 7E rejected). Sample: N=2 fills = INSUFFICIENT_SAMPLE (never evidence). Multiple testing: NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY.
    TESTS: new tests/test_researcher_15.py (33 tests, all 25 mandated areas); zero modified tests (WEAKENING none by construction); pytest 2904/2904/0 reconciled; unittest discover TIMEOUT (honestly reported); compileall clean (scoped + full). Determinism: Phase-15 artifact regenerated byte-identical (sha256 044e9e2c...); no parallel paths (worker-invariance N/A, tested). Isolation (FORBIDDEN-token + mock guards), security (env-refs only; history = operator action) green. Artifact: research/results/phase15_evidence_readiness.json (all 25 orders, scenarios, gate matrix; is_production_ready False).
    EDGE = NOT ESTABLISHED. EXECUTABILITY = LOW_EXECUTABLE_OPPORTUNITY. OOS: infrastructure AVAILABLE, evidence ABSENT. OUTCOME: OOS_EXECUTION_BLOCKED + DATA_LIMITED (operator must supply ~75k+ fresh 1m bars + fee/funding schedules + microstructure before any OOS execution; no fetching performed -- phase stays offline/deterministic). PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.
149. **Phase 16 (Evidence-Readiness Regression; Research-Only Helpers)**.
    READINESS-REGRESSION ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-15 baseline from source (HEAD 1b26905; Gate-A 25/2/0W/2L/-0.206452 PASS byte-identical via tests/test_readiness_16.py TestBaselineReproduction; pytest 2940 collected = 2904 + 36 readiness-16, all green with per-file reconciliation).
    NEW HELPERS (research-only, pure deterministic, no production imports, no I/O/network/randomness): core/research/readiness/__init__.py + sample_math.py (expected_orders/expected_fills/required_bars/oos_span_bars/sample_ladder over caller-supplied rates; required_bars(10, 0.005, 0.08) = 25000.0 pinned; oos_span_bars 6-period + discovery headroom pinned) + scenarios.py (scenario_structural VERIFIED-zero-cost identity; scenario_conservative_fees/slippage/combined ASSUMED 2.5bp/1bp-per-side round-trip; scenario_funding UNAVAILABLE with net None, zero NEVER substituted).
    TESTS: new tests/test_readiness_16.py (36 tests, all 25 mandated areas as regression: baseline, dataset hash/stable + classification, instrument semantics + no-notional pin, fees/funding/microstructure, cost scenarios, venue, temporal split + OOS gate/protocol frozen, sample ladder + math, actual-fill RR >= 6, favorable-gap refusals 0, regime/symbol/directional, multiple-testing, lookahead exec>=trigger+1, serialization byte-stable, worker scope, production posture, 11G + strategy-hash pins); zero modified tests (WEAKENING none by construction); related suites green (test_researcher_15 33 + test_edge_forensics_14 22 = 55/55); compileall clean (scoped readiness + test file); full collection 2940/2940 with zero collection errors.
    EDGE = NOT ESTABLISHED. EXECUTABILITY = LOW_EXECUTABLE_OPPORTUNITY. OOS: infrastructure AVAILABLE, evidence ABSENT. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.
150. **Phase 17 (Independent Data Acquisition & Genuine OOS Feasibility)**.
    ACQUISITION/FEASIBILITY ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-16 baseline from source (HEAD 6ae3aa7; Gate-A 25/2/0W/2L/-0.206452 PASS byte-identical via tests/test_oos_feasibility_17.py TestStrategyIdentity; 9-file strategy hash c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6 pinned; MIN_RISK_REWARD 6.0 + BREAKOUT_CONTINUATION-only pinned).
    NEW ACQUISITION LAYER (research-only, pure deterministic, no strategy/execution imports): core/research/acquisition/__init__.py + provenance.py (ProvenanceManifest frozen canonical fields, manifest_id sha256 over canonical only via frozen 11G content_hash, fetched_at wall-clock EXCLUDED, closed COMPLETE/PARTIAL/EMPTY/BLOCKED) + quality.py (audit_quality over {time,open,high,low,close,volume}, duplicates/gaps/OHLC/malformed counted, flat/zero-volume COUNTED never classified PROVENANCE_UNKNOWN) + feasibility.py (recalculate_requirements/budget_periods over frozen Phase-16 sample_math, OOS_FEASIBLE/OOS_BLOCKED only, no ranking/selection/optimization).
    OPERATOR SCRIPTS (read-only, no strategy): scripts/fetch_phase17_fresh.py (HistoricalLoader.candles_paginated strictly after Gate-A end 1788601440, git-ignored cache data/history/BTCUSDT_1m_phase17_fresh.json + .provenance.json) + scripts/build_phase17_artifact.py (deterministic given inputs: reads committed Gate-A/P14/P15 + fresh cache + venue product snapshot, writes research/results/phase17_oos_feasibility.json indent=2 sort_keys).
    FRESH DATA: BTCUSDT 1m 11461 bars strictly after Gate-A (1788601500 -> 1789289100, ~8.0d), coverage 1.0, 0 gaps/dupes/OHLC-violations/malformed, flat 95.0% / zero-volume 88.0% PROVENANCE_UNKNOWN, rows carry no venue tag (manifest-level DELTA only, row-level provenance ABSENT); strategy never ran on fresh data (readiness-checks only, no fills/trades/pnl in cache).
    SAMPLE: measured order_rate 0.005 (25/5000) x fill_rate 0.08 (2/25) -> 25000 bars/period, 150k OOS span, 300k total (lower bound; N=2 unbounded above); fresh 11461 -> 0 adequate 10-fill periods of 6 required -> OOS_BLOCKED (wall-clock bound, not engineering).
    TESTS: new tests/test_oos_feasibility_17.py (27 tests, 9 classes: identity/provenance/quality/sample/fresh-discipline/contamination/determinism/posture/frozen-boundaries); zero modified tests (WEAKENING none); verified unittest 27/27 green in 3.7s; artifact byte-stable (sort_keys regen hash match); full pytest suite NOT re-run in this session (single-file pytest collection timed out >120s; canonical 2940 baseline preserved).
    EDGE = NOT_ESTABLISHED. EXECUTABILITY = LOW_EXECUTABLE_OPPORTUNITY. OOS: infrastructure AVAILABLE, evidence ABSENT. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.
151. **Phase 18 (Frozen-Strategy Genuine Multi-Period OOS Validation)**.
    OOS-VALIDATION ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-17 baseline from source (HEAD 6eb35d8; Gate-A 25/2/0W/2L/-0.206452 + 9-file hash c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6 pinned; MIN_RISK_REWARD 6.0 + BREAKOUT_CONTINUATION-only pinned; fresh 11461 bars hash 247d8f11dcd34d49 strictly after Gate-A 1788601440 verified).
    NEW VALIDATION LAYER (research-only, deterministic, no strategy/execution invention): core/research/oos_validation/__init__.py + periods.py (validate_freshness strict timestamp>boundary + split_bars 6 equal chronological OOS_01..OOS_06, no shuffle) + execution.py (run_frozen_oos: frozen Backtester + InstitutionalPipeline defaults per slice, mutually-exclusive terminal counts, realized_rr via canonical accounting, no ledger/live mutation) + report.py (classify_period 10-trade settling gate + aggregate_results + decide_final over frozen 9M constants, no ranking/selection).
    GENUINE EXECUTION (frozen path, ~60s global + 6x~10s per-period): global continuous 11461 bars -> 32 orders (30 EXPIRED/2 INVALIDATED) 0 fills 0 trades; per-period independent OOS_01 1910b 2E/0F, OOS_02 1910b 0/0, OOS_03 1910b 2E/0F, OOS_04 1910b 1E/1I/1P/0F, OOS_05 1910b 8E/0F, OOS_06 1911b 0/0 (15 orders total; cold-start warmup explains global-vs-per-period gap; 0 fills everywhere).
    ECONOMICS/CONSISTENCY: structural VERIFIED-zero-cost net 0.0; fees/slippage ASSUMED-schedule UNAVAILABLE-no-notional with 0 fills; funding UNAVAILABLE (zero NOT substituted); microstructure UNAVAILABLE; single symbol BTCUSDT INCONCLUSIVE; LONG/SHORT asymmetry not assessable (0 fills); regime UNAVAILABLE; survival 0/6 (2 UNAVAILABLE + 4 INCONCLUSIVE).
    TESTS: new tests/test_oos_validation_18.py (30 tests: identity/boundary/periods/sample-RR/semantics/economics/consistency/honesty/lookahead/determinism/posture/frozen-boundaries); zero modified tests; unittest 30/30 green; artifact byte-stable regen hash 95cef0271ae746f2; full pytest suite NOT re-run (collection timeout, preserved baseline).
    EDGE = NOT_ESTABLISHED. OOS: infrastructure AVAILABLE, genuine execution PERFORMED, evidence INSUFFICIENT (0 trades). FINAL = OOS_BLOCKED. PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.
152. **Phase 19 (Independent OOS Data Extension & Executable-Sample Accumulation)**.
    DATA-EXTENSION ONLY: strategy/thresholds/RR/execution frozen; no tuning, no promotion, no live. Reproduced Phase-18 baseline from source (HEAD 031de0d; OOS_BLOCKED 0 fills/11461 bars; 9-file hash c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6 pinned; MIN_RISK_REWARD 6.0 + BREAKOUT_CONTINUATION-only pinned; boundary 1788601440 strict).
    NEW EXTENSION LAYER (research-only, deterministic, Tier A direct only): core/research/extension/__init__.py + extension.py (dedupe_merge strict-boundary/dedupe/no-gap-fill + extension_stats + estimate_extension zero-fills->None/UNAVAILABLE, stdlib-only) + scripts/fetch_phase19_extension.py (operator-run read-only HistoricalLoader merge with Phase-17 cache, git-ignored extension cache) + scripts/build_phase19_artifact.py (deterministic builder: 6 per-period + 1 global frozen runs over merged span).
    EXTENSION MEASURED: prior 11461 bars (1788601500->1789289100) + 438 new bars -> merged 11899 bars (1788601500->1789315380); quality 0 dupes/gaps/OHLC/malformed, flat ~95% / zero-volume ~88% PROVENANCE_UNKNOWN persists; rows carry no venue tag; Tier B/C/D not used (no proxy/synthetic).
    GENUINE EXECUTION (frozen path over merged 11899): per-period 6x~1983b 0 fills everywhere; global continuous 0 fills; 0 completed trades total (<60 required, <10/period); bars_per_fill None (ZERO OBSERVED FILLS, no division by zero); additional-data requirement not finitely inferable from zero (lower-bound context only, unbounded above).
    TESTS: new tests/test_oos_data_extension_19.py (25 tests covering 29 areas); zero modified tests; unittest 25/25 green (57/57 with Phase-18, 82/82 with Phase-17/18); artifact byte-stable regen hash 95537d42d1459f51; full pytest suite NOT re-run (collection timeout, preserved baseline).
    EDGE = NOT_ESTABLISHED. OOS_FEASIBILITY = BLOCKED (DIRECT_OOS_DATA_LIMITATION: wall-clock bound, 438 new bars). PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.
153. **OOS Execution Readiness + Top-Up Acquisition + Readiness Monitor (research-only; strategy frozen, protocol untouched, no execution)**.
    PREREGISTRATION (new minimal authority; none existed): core/research/readiness/preregistration.py (FrozenPreregistration, immutable, content_hash identity, refuses 7E + production-ready). READINESS EVALUATOR: core/research/readiness/oos_execution_readiness.py (explicit arithmetic only: 6175 contiguous 11G-Q gate, 300000 fresh-bar frozen derivation at measured Gate-A rates 0.005/0.08, 60-fill evidence gate; missing stays UNAVAILABLE/BLOCKED, never passes). Real verdict then: BLOCKED (boundary/contiguity/overlap/identity VERIFIED on 11899 bars; span/fills/economics/microstructure BLOCKED).
    TOP-UP ACQUISITION (public data only): scripts/fetch_oos_topup.py (operator-run read-only HistoricalLoader + dedupe_merge into NEW git-ignored data/history/BTCUSDT_1m_oos_topup.json; Phase-17/19 caches byte-untouched). Result 11899 -> 29491 genuine post-boundary bars (identity 75e8338f...; 0 duplicates; gaps preserved). Economics observation fixture added (venue docs + MCP corroboration: maker/taker PARTIAL, funding PARTIAL, slippage/contract-value UNAVAILABLE; nothing provisioned into costs.py). Microstructure UNAVAILABLE (venue: recent trades only). Fills 0 (no eligible hypotheses; nothing simulated).
    READINESS MONITOR (this entry): core/research/readiness/monitor.py reuses the evaluator (no second engine): run_monitor() -> evaluate -> deterministic ReadinessSnapshot (content_hash id, arithmetic gaps from source timestamps only, no wall-clock) -> classified blockers (DATA_TIME_BOUND / DATA_INSUFFICIENT / NO_ELIGIBLE_HYPOTHESES / NO_FILLS / ECONOMICS_UNAVAILABLE / MICROSTRUCTURE_UNAVAILABLE / PREREGISTRATION_REQUIRED / OPERATOR_PREREQUISITE / REPOSITORY_FORENSIC_BLOCK) -> terminal handoff (WAITING_FOR_DATA / ... / READY_FOR_PREREGISTRATION / READY_FOR_OOS_EXECUTION; READY never executes -- no execution path exists). NO_NEW_SOURCE_DATA is a normal condition. Unprovenanced rows get OPERATOR_PREREQUISITE (synthetic futures can never pass as genuine). Real snapshot: BLOCKED / WAITING_FOR_DATA, fresh gap 270509, fill gap 60.
    TESTS: tests/test_oos_execution_readiness.py (28) + tests/test_oos_topup_acquisition.py (18) + tests/test_readiness_monitor.py (21), stdlib-only offline; determinism/lookahead(A-F)/isolation green; historical pins preserved untouched.
    EDGE = NOT_ESTABLISHED. OOS_EXECUTION_READINESS = BLOCKED (time-bound data + 0 fills + 0 hypotheses + economics/microstructure). PAPER = CONDITIONAL. LIVE = NO-GO. SECURITY = BLOCKED. PRODUCTION_READY = False.



## LEVEL 4 — R:R / EXIT POLICY WORK

154. **LEVEL 4 RUNTIME R:R / EXIT POLICY AMENDMENT — GLOBAL + INSTRUMENT CONFIGURATION**. Runtime trading policy is now `core/risk/trading_policy.py`: inclusive 1:1 minimum through 1:20 maximum, global defaults plus exact instrument overrides, deterministic persisted JSON, authenticated `/risk-policy` GET/POST/reset routes, and frontend controls. Runtime trades validate their authored target under the selected instrument policy before trailing management is attached. Trailing management is enabled by default at 1.0R activation / 0.5R distance, is operator-changeable per instrument, and may close at trailing stop, target, explicit exit/book-profit signal, or enabled opposite-direction signal. The frozen research `MIN_RISK_REWARD=6.0` remains untouched. Tests: 18 Level-4/policy tests green; risk/execution/lifecycle regression 75/75 green; compileall clean. LIVE trailing routing remains BLOCKED until venue trailing/OCO execution is independently evidenced. PRODUCTION_READY remains FALSE.

Level 3 remains the frozen evidence/OOS readiness checkpoint. Level 4 changes the TRADING execution fixed-target reward:risk policy to
an inclusive 1:1 minimum and 1:20 maximum; the frozen Level-3 research/OOS
MIN_RISK_REWARD=6.0 identity is intentionally unchanged. A separate TRAILING_STOP exit mode is represented in
the setup/order/trade contracts and is fail-closed by default until its
operator-provisioned trailing parameters and venue execution contract
are explicitly enabled. Paper/backtest trailing management is close-based
and deterministic; live execution remains blocked for trailing mode.
Production readiness remains FALSE.

155. **LEVEL 4 RUNTIME RR AUTHORITY CLOSURE + POSITION-RATIO SEMANTICS**. The runtime DecisionEngine and RiskEngine now both consume the same `core.risk.trading_policy` authority: inclusive 1:1 minimum through 1:20 maximum, with exact-instrument overrides resolved before order validation. RiskEngine now carries the computed price-derived RR into `OrderIntent` instead of trusting a self-reported signal RR field. The misleading `PositionSize.risk_reward` alias was retired; `notional_to_risk` remains the notional multiple and `reward_to_risk` remains the true entry/stop/target ratio. Runtime tests were updated to prove 0.99 rejects, 1.0 accepts, 5.0 accepts, 20.0 accepts, 20.01 rejects, and lying RR fields cannot override price-derived validation. Focused runtime/risk/execution suite: 99/99 green; API/risk-policy suite: 29/29 green; 9M/9N/9O + Level-4 suite: 174/174 green; compileall clean. Frozen research `MIN_RISK_REWARD=6.0` remains a research artifact and was not changed.

156. **GLOBAL PUBLIC SOCKET EVIDENCE ATTEMPT — EXTERNAL ENVIRONMENT BLOCKED**. A bounded 330-second credential-free Global `BTCUSDT` capture was attempted against `wss://public-socket.delta.exchange` with `trades,candlestick_1m,ob_l1,ticker` and control-frame retention. The attempt failed before socket establishment with `socket.gaierror: Temporary failure in name resolution`. No frames were accepted as evidence, no verifier PASS was claimed, and no runtime transport was enabled from this attempt. The Global rollover/server-recovery gate therefore remains BLOCKED.

157. **PAPER ECONOMICS AUTHORITY CLOSURE + LEVEL-4 POLICY REGRESSION**.
    Closed a genuine runtime split-brain: `core/paper_trading/paper_trading_engine.py`
    now consumes `core.risk.costs.paper_cost_profile()` for actual paper-fill
    commission/slippage instead of silently using production OrderIntent cost
    fields. Post-cost R:R remains enforced at the shared TradeSimulator choke.
    Explicit `fill_slippage_bps` remains an additional fill-price model, not a
    substitute for round-trip accounting costs. Runtime policy remains global
    1:1..1:20 with trailing enabled by default and exact instrument overrides.
    Paper-preview tests were updated only where the authenticated risk-policy
    control surface intentionally supersedes the old "no controls" assertion;
    order/trading mutation routes remain prohibited. `.vscode/mcp.json` was
    restored in the testnet-only `servers.delta-exchange-mcp.env` shape after
    the ZIP snapshot omitted the file.
    TESTS: affected paper/risk/execution/preview/lifecycle regression 148/148
    PASS; research/readiness/MCP secondary suite 119/119 PASS; compileall PASS.
    Two old Phase-7 normalized-digest pins remain historical forensic failures
    and were not re-pinned. Global public-socket rollover/server-recovery
    evidence remains externally BLOCKED; no venue evidence was fabricated.
    EDGE = NOT ESTABLISHED. OOS = BLOCKED. LIVE = NO-GO. PRODUCTION_READY = False.

158. **Phase 20 — OOS ROW-LEVEL PROVENANCE HARDENING.** Added deterministic
    row-level provenance sidecar for the existing Tier-A DELTA BTCUSDT 1m OOS
    top-up cache. The raw venue-verbatim candle schema is unchanged. Every
    accepted timestamp now has an exact provenance record containing venue,
    acquisition source/method, symbol and timeframe; the sidecar has its own
    deterministic SHA-256 identity and exact timestamp-coverage validator.
    Existing top-up data was not reacquired or altered; this phase adds
    provenance to the already observed acquisition artifact only. Tests:
    tests/test_oos_row_provenance_20.py + top-up acquisition = 25 passed, 1
    skipped when no operator-generated sidecar exists; current snapshot now
    contains the sidecar and therefore real-artifact checks pass. This closes
    the row-level provenance *recording* gap, but does not independently
    authenticate venue origin. OOS remains BLOCKED; EDGE NOT ESTABLISHED;
    LIVE NO-GO; PRODUCTION_READY=False.

---

## PHASE 32 — STRICT OOS ACQUISITION ACCUMULATOR

- **IMPLEMENTED:** `core/research/acquisition/accumulator.py` adds a deterministic, research-only batch accumulation seam for future Tier-A OOS top-ups.
- **SAFETY:** every accepted batch must be strictly after the frozen Gate-A boundary and have exact row-level provenance coverage. Identical timestamp/payload duplicates are deduplicated; conflicting same-timestamp OHLCV or provenance records fail closed rather than using first-wins behavior. No gaps are filled and no interpolation occurs.
- **IDENTITY:** batch and merged-dataset identities reuse the existing canonical SHA-256 construction semantics; no UUIDs, randomness, or wall-clock state enter identities.
- **INTEGRATION:** `scripts/fetch_oos_topup.py` now uses the strict accumulator for subsequent operator-run acquisitions. The frozen Phase-19 dataset is never overwritten.
- **REAL-CACHE CHECK:** the existing 30,247-row Phase-30 cache validates exactly against its stored dataset identity and row-provenance coverage.
- **TESTS:** Phase-32 accumulator tests = 7/7 PASS; acquisition/top-up regression = 24/25 PASS in this ZIP snapshot. The single error is the pre-existing `test_h_phase19_cache_untouched` expectation for `data/history/BTCUSDT_1m_phase19_extension.json`, which is absent from the supplied Phase-30 ZIP; the test was not modified or weakened.
- **PRODUCTION:** `production_ready=False`; no execution authority, strategy mutation, order submission, or promotion was added.
- **OOS:** remains `OOS_BLOCKED`; genuine completed trades remain 3/60 and no current 9L hypothesis is preregistered.

## PHASE 22 — DELTA MCP RESEARCH ADAPTER (2026-09-27)

- **IMPLEMENTED:** `research/integrations/delta_mcp.py` adds a research/operator-only boundary for the current Delta Exchange MCP server contract.
- **SOURCE:** current Delta MCP docs identify `delta-exchange-mcp` v0.7.0 beta as a local stdio server; 14 public market-data tools require no key, while account/trading tools require credentials/permissions.
- **SAFETY:** default environment is `india_testnet`; public tools are explicitly allowlisted; trading authority is rejected; no credential material is stored or read by the adapter.
- **ISOLATION:** adapter is under `research/`, not `core/`; production modules do not consume MCP configuration.
- **TESTS:** `tests/test_delta_mcp_adapter_22.py` = 5/5 PASS; existing MCP config/public-evidence tests = 16/16 PASS; compileall clean.
- **EXTERNAL LIMITATION:** `uvx delta-exchange-mcp` could not be launched in this execution environment because DNS resolution to PyPI is unavailable. No external MCP observation was fabricated.
- **PRODUCTION READINESS:** FALSE.

## PHASE 24 — DELTA MCP PUBLIC OBSERVATION NORMALIZATION (2026-09-28)

- **IMPLEMENTED:** `research/integrations/delta_mcp_observations.py` adds a deterministic, research-only normalization boundary for already-received Delta MCP public responses.
- **PUBLIC SURFACE:** The adapter accepts only the existing allowlisted public tools; it does not invoke MCP, REST, WebSocket, account, or trading authority.
- **NORMALIZATION:** Candles, recent trades, mark-price history, funding history, OI history, settlement prices, products, tickers, order books, option chains, indices, and reference data are classified without inventing missing venue fields.
- **FAIL-CLOSED:** Response-envelope failures, symbol mismatches, malformed numeric values, invalid candle OHLC relationships, and unsupported tools are rejected or marked UNAVAILABLE/PARTIAL.
- **DETERMINISM:** Every normalized observation receives a SHA-256 content identity derived from canonicalized observed response content; repeated identical observations produce identical identities.
- **AUTHORITY BOUNDARY:** This phase does not claim venue authenticity merely from a normalized response. Raw MCP capture/provenance remains an upstream requirement for external evidence certification.
- **TESTS:** `tests/test_delta_mcp_observations_24.py` = 11/11 PASS; compileall clean.
- **EXTERNAL LIMITATION:** No live MCP observation was fabricated; external network/MCP access remains environment-dependent.

## PHASE 25 — DELTA MCP PUBLIC EVIDENCE BUNDLE (2026-09-28)

- **IMPLEMENTED:** `research/integrations/delta_mcp_evidence_bundle.py` combines already-normalized public MCP observations into a deterministic research-only evidence bundle.
- **DOMAINS:** product, candles, trades, orderbook, open interest, funding, mark price, settlement, options, and indices are represented explicitly; absent domains remain `UNAVAILABLE`.
- **CONSISTENCY:** symbol mismatches, duplicate domains, and unsupported observations are retained as explicit bundle errors rather than silently overwritten.
- **DETERMINISM:** bundle identity is derived only from symbol, observation tool/status/content identities, domain status, and consistency errors; repeated identical inputs produce byte-identical bundle identities.
- **AUTHORITY:** `venue_authentication` is permanently `UNVERIFIED`; this phase cannot self-certify venue origin.
- **SAFETY:** no MCP invocation, network access, credentials, account data, order submission, ledger mutation, or production import is introduced.
- **TESTS:** `tests/test_delta_mcp_evidence_bundle_25.py` + Phase-22/24 MCP suites = 22/22 PASS; compileall clean.
- **EXTERNAL LIMITATION:** genuine Delta MCP observations remain environment-dependent; no synthetic observation is promoted to external evidence.
- **PRODUCTION READINESS:** FALSE.

## PHASE 26 — DELTA MCP → 9I RESEARCH BRIDGE (2026-09-28)

- **IMPLEMENTED:** `research/integrations/delta_mcp_research_bridge.py` consumes an already-built Delta MCP public `EvidenceBundle` and converts each documented domain into the existing Phase-9I `ResearchRow` model using the closed `RESEARCH` source. The frozen 9I row schema and `DatasetSource` vocabulary were not modified.
- **DOMAIN VISIBILITY:** all ten MCP evidence domains remain visible; absent domains become explicit `UNAVAILABLE` research rows rather than disappearing. PARTIAL/VERIFIED status, missing fields, consistency errors, bundle identity, and observation identity are retained in the row evidence bags.
- **DETERMINISM:** row IDs remain the canonical 9I deterministic IDs; identical bundles produce byte-identical dataset serialization and row identities.
- **AUTHORITY:** `venue_authentication=UNVERIFIED` is preserved verbatim. The bridge cannot promote MCP observations to venue-authenticated evidence and cannot alter production/runtime decisions.
- **ISOLATION:** bridge lives under `research/integrations/`; it has no production execution/broker/live imports and performs no MCP/network/account/trading calls.
- **ARTIFACT:** `research/results/phase26_mcp_9i_bridge.json` is a deterministic bridge demonstration artifact only; it is not external venue evidence.
- **TESTS:** Phase-26 bridge + Phase-22/24/25 MCP suites = 48/48 PASS; compileall clean.
- **PRODUCTION READINESS:** FALSE; genuine MCP venue evidence remains dependent on an external MCP/network execution environment.

## PHASE 27 — DELTA MCP → 9J DISCOVERY CONTEXT (2026-09-28)

- **IMPLEMENTED:** `research/integrations/delta_mcp_discovery_context.py` reads only existing Phase-9I `RESEARCH` rows produced by the Delta MCP bridge and summarizes public-data domain availability for the 9J discovery report.
- **BOUNDARY:** MCP context does not create hypotheses, modify candidate generation, bypass 9J/9K/9L/9M gates, or certify venue authenticity.
- **AUTHENTICATION:** remains `UNVERIFIED` unless independently certified by the external evidence protocol.
- **VERIFICATION:** Phase-27 context tests + 9J/9K/9M regression = 132/132 PASS; compileall PASS.
- **PRODUCTION-READINESS:** FALSE.

## PHASE 28 — DELTA MCP → 9K REGIME/CONDITIONING CONTEXT (2026-09-28)

- **IMPLEMENTED:** `research/integrations/delta_mcp_regime_context.py` provides a research-only context boundary for the existing Phase-9K regime engine. MCP public domains that can be useful as contextual evidence (trades, orderbook, open_interest, funding, mark_price, settlement, options, indices) are surfaced only as **available conditioning domains**.
- **NO REGIME FABRICATION:** MCP observations are never mapped directly to `TREND`, `RANGE`, direction, volatility, ATR, displacement, liquidity, Wyckoff, FVG, or order-block labels. Those labels remain detector-derived, decision-time, closed-vocabulary, and sample-gated inside 9K.
- **INTEGRATION:** `OpportunityDiscoveryEngine` adds deterministic MCP conditioning limitations to the existing `RegimeReport`; 9K cells, findings, walk-forward validation, multiple-testing, and robustness calculations are unchanged.
- **AUTHORITY:** `venue_authentication=UNVERIFIED` is preserved. MCP context cannot establish a regime-conditioned trading claim and cannot bypass 9K/9M/OOS or production-readiness gates.
- **TESTS:** Phase-28 + Phase-27 + Phase-22/24/25/26 MCP suites + `test_researcher_9k` = **132/132 PASS**; `python -m compileall -q .` = **PASS**.
- **EXTERNAL LIMITATION:** no genuine MCP venue observation was created or promoted in this phase.
- **PRODUCTION READINESS:** `FALSE`.

148. **Phase 30 (Fresh Genuine OOS Evidence Accumulation).**
    Consumed the existing Tier-A direct Delta BTCUSDT 1m post-Gate-A cache (30,247 rows; row-provenance identity `2b07b61a…6c9c`) without changing the frozen strategy or 9M gates. Replayed six independent chronological periods through the existing frozen OOS execution seam. Observed 21 orders and 3 completed trades: 1 win / 2 losses; aggregate structural gross P/L -0.21969293. No period reached the 10-trade settling threshold; 5 periods are INCONCLUSIVE and 1 is UNAVAILABLE. Therefore 9M remains **OOS_BLOCKED** (3/60 completed trades; 0/6 settled periods; 0 hypotheses revalidated). No 9L hypothesis was invented or inferred from legacy 11G-K artifacts. Added deterministic `scripts/build_phase30_oos_evidence.py`, artifact `research/results/phase30_oos_evidence_accumulation.json`, and `tests/test_phase30_oos_evidence.py`. `production_ready=False`; EDGE=NOT_ESTABLISHED; no promotion.

## PHASE 33 — DETERMINISTIC CURRENT OOS READINESS SNAPSHOT

Phase 33 binds the current genuine Phase-30/32 BTCUSDT 1m OOS cache to the
existing `core.research.readiness.monitor` and `oos_execution_readiness`
contracts. It adds no second readiness engine and performs no OOS execution.

Artifact:
`research/results/phase33_oos_readiness_snapshot.json`

Current deterministic snapshot:
- dataset identity: `520b849b6612335d4987161d67b5163939bf9e20019dd5a25ec02b876a2310b0`
- fresh bars: 30,247 / 300,000 required
- fill evidence: 3 / 60 required
- readiness: `BLOCKED`
- handoff: `WAITING_FOR_DATA`
- source status: `NO_NEW_SOURCE_DATA`
- hypotheses: 0
- duplicate rows: 0
- OHLC violations: 0
- missing 1-minute intervals: 185 (reported, never filled)
- coverage: 99.3921% over the observed timestamp span
- flat bars: 95.2326%; provenance remains `PROVENANCE_UNKNOWN`
- zero-volume bars: 88.3162%; provenance remains `PROVENANCE_UNKNOWN`
- production-ready: `FALSE`

The snapshot is byte-identical on repeated execution and binds the exact
current dataset/provenance identities. It is a readiness/accounting artifact,
not a profitability result and not an OOS validation.

External source acquisition remains blocked by the current environment's DNS
failure; no synthetic or proxy observations were inserted.


## PHASE 34 — DETERMINISTIC OOS ACQUISITION ANCHOR

- OOS acquisition now requires an explicit `--end-timestamp` anchor; the operator no longer derives its request span from wall-clock time.
- `HistoricalLoader.candles_paginated()` accepts an optional deterministic `end_timestamp` while preserving historical behavior for existing callers that omit it.
- No gap filling, interpolation, provenance weakening, or production execution is introduced.
- Current genuine OOS evidence remains unchanged: 30,247 fresh bars and 3 completed fills; 9M remains `OOS_BLOCKED`.
- Phase 34 is research-only; `is_production_ready` remains permanently `False`.
- Full repository certification remains unavailable in this ZIP snapshot because historical Phase-17 fixtures are absent and frozen historical identity/artifact-byte assertions remain unresolved.


## PHASE 35 — MULTI-SYMBOL OOS EVIDENCE COVERAGE

Phase 35 adds a deterministic research-only per-symbol coverage audit. Rows are attributed to a symbol only when explicit row-level symbol metadata exists; filenames are never used to synthesize symbol evidence. The current 30,247-row OOS candle cache contains 30,247 rows without explicit symbol fields, so cross-symbol coverage is UNAVAILABLE. No universal validation claim is made. Production readiness remains permanently FALSE.

## PHASE 36 — PROVENANCE-BOUND SYMBOL COVERAGE

Phase 36 extends the existing Phase-35 symbol coverage audit to consume the
already-bound Phase-20 row-level provenance sidecar. It does not infer a
symbol from filenames or the cache envelope. Symbol attribution is accepted
only when the provenance timestamp set exactly covers the candle rows and no
conflicting provenance exists. The existing 30,247-row dataset therefore
has 30,247 rows attributable to BTCUSDT through bound provenance, while
cross-symbol evidence remains unavailable because only one symbol is
present. OOS trade/period gates remain unmet and production readiness remains
permanently FALSE.

Artifact: `research/results/phase36_provenance_symbol_coverage.json`
- symbol source: `row_level_provenance`
- observed symbols: 1 (`BTCUSDT`)
- symbol-attributed rows: 30,247
- missing symbol rows: 0
- cross-symbol validation: `UNAVAILABLE`
- OOS validation: `BLOCKED`
- production-ready: `FALSE`

## PHASE 37 — MULTI-SYMBOL OOS ACQUISITION MANIFEST

Implemented a research-only deterministic multi-symbol acquisition manifest.
Each symbol retains an independent validated row/provenance namespace; identical timestamps across different symbols are not merged. Duplicate symbol declarations and provenance mismatches fail closed. Current evidence remains single-symbol BTCUSDT, so cross-symbol validation remains UNAVAILABLE.

Status: IMPLEMENTED / TESTED / VERIFIED
Production readiness: FALSE

## PHASE 38 — MULTI-SYMBOL OOS AGGREGATION

- Added deterministic research-only cross-symbol aggregation in `core/research/readiness/symbol_aggregation.py`.
- Per-symbol OOS states remain independent; missing symbols are not converted into rejection.
- `UNAVAILABLE`, `INCONCLUSIVE`, and `REJECTED` remain distinct.
- Current evidence: one provenance-bound BTCUSDT symbol; second required symbol absent; cross-symbol evidence remains `UNAVAILABLE`.
- Added deterministic Phase-38 artifact and tests.
- Production readiness remains permanently `FALSE`.

## PHASE 39 — FROZEN 9M PREREGISTRATION RELOAD INTEGRITY

- Added deterministic `FrozenPreregistration.from_dict()` as the single sanctioned persisted-artifact reload path.
- Reload is fail-closed for missing fields, malformed hypotheses, tampered identity content, and any persisted `is_production_ready=True` value.
- Round-trip `to_dict() -> from_dict() -> to_dict()` is byte-identical and `verify_identity()` remains true.
- No hypothesis is generated, selected, promoted, or inferred by this phase.
- Phase 39 focused research/readiness regression: 60/60 PASS.
- `python -m compileall -q .`: PASS.
- Real OOS state remains `OOS_BLOCKED`; no current 9L hypothesis set is preregistered.
- `is_production_ready` remains permanently `False`.

## PHASE 43 — RESEARCH BOUNDARY + FROZEN 9L→9M HANDOFF CHECKPOINT

- Hardened `ConditionalMlReport` identity so every persisted report-defining surface participates in its deterministic identity.
- Added strict `ConditionalMlReport.from_dict()` canonical reload/tamper rejection.
- Added explicit `NineLSelection` admission for supported 9L recovery/entry findings; no automatic selection or promotion.
- Added explicit 9L selection → `FrozenPreregistration` handoff with provenance validation.
- Added `OosValidationEngine.run_preregistered()` as the frozen execution seam; it refuses preregistration identity drift, dataset drift, protocol drift, and hypothesis-order drift.
- Added research import-boundary tests proving the OOS/readiness/conditional-ML research packages do not import production runtime modules.
- Focused regression: 85/85 PASS; `python -m compileall -q core tests scripts`: PASS.
- Full repository certification remains NOT CERTIFIED because preserved historical Phase-17/18 strategy/artifact identity assertions do not match the current source snapshot.
- Genuine 9M remains `OOS_BLOCKED`; no profitability or production-readiness claim is made.
- `is_production_ready=False` remains permanent.

Artifact: `research/results/phase43_checkpoint.json`

## PHASE 56 — DETERMINISTIC OOS BUILDER HARDENING

Implemented deterministic hardening for `scripts/build_phase17_artifact.py`.
The builder now has no network acquisition path and requires the pre-existing
`data/history/BTCUSDT_product_phase17.json` venue snapshot. Missing evidence
fails closed with `MISSING_PRODUCT_SNAPSHOT`; the builder never silently fetches
replacement venue metadata. Standalone CLI execution now bootstraps the
repository import path. This is research-only and does not alter production
execution or readiness (`production_ready=false`).

Validation: Phase-56 builder/readiness focused tests PASS; `compileall` PASS.

## PHASE 57 — EXPLICIT PRODUCT SNAPSHOT ACQUISITION BOUNDARY

Added `scripts/acquire_phase17_product_snapshot.py` as the separate
credential-free, read-only network acquisition step for the Phase-17 Delta
product snapshot. The caller must supply `--observed-label`; acquisition does
not use wall-clock time, UUIDs, or credentials. It reuses the existing
`DeltaProducts` adapter and writes the declared snapshot atomically.

The deterministic `build_phase17_artifact.py` remains network-free and only
consumes the pre-existing snapshot. Missing/ambiguous BTCUSDT evidence fails
closed. `production_ready=false` remains mandatory.

Validation: Phase-57 tests PASS; Phase-56/OOS focused tests PASS; compileall PASS.

## PHASE 58 — PHASE-CONTINUITY / LOSS-PREVENTION AUDIT

A source-backed continuity audit was performed against the latest checkpoint.
Phase state is classified as PRESENT, RESTORED_PHASE58, PARTIAL,
DOCUMENTED_BOUNDARY_ONLY, or MISSING_GENUINE_ARTIFACT. Narrative phase claims
are never treated as proof when source/test/artifact evidence is absent.

The continuity manifest is:
`research/results/phase58_phase_continuity.json`

Important: the historical genuine Phase-49 9L result is not reconstructed or
fabricated. Its original evidence artifact is unavailable in this checkpoint.
Phase-55's historical recertification boundary is preserved as a constraint,
not falsely represented as a recovered executable artifact.

Production readiness remains permanently FALSE.

## PHASE 59 — PHASE-CONTINUITY RESTORATION + RECOVERY CHECKPOINT

- Restored durable Phase-47 9A journal persistence using the existing `ResearchRepository`: schema `9A-journal-v1`, deterministic content identity, atomic persistence, strict reload, and tamper/missing-identity rejection. No second journal system created.
- Restored Phase-48 deterministic 9A discovery capture through the existing `Backtester -> ResearchJournal` observer path. Artifact: `research/results/phase48_discovery_capture.json`.
- Preserved Phase-49 as `MISSING_GENUINE_ARTIFACT`; its historical genuine Binance 9L result is not reconstructed without its original evidence/data.
- Created `research/results/phase55_recertification_boundary.json` from the current source-backed recertification check. Historical digest remains preserved and mismatched; no historical artifact was recreated.
- Created `research/results/phase59_continuity.json` as the authoritative source/test continuity manifest. Source and test evidence outrank narrative phase summaries.
- Focused continuity + restored Phase-47/48 + frozen handoff + Phase-56/57 regression: **24/24 PASS**.
- `python -m compileall -q core tests scripts`: **PASS**.
- Production readiness remains permanently `FALSE`.
- This phase does not claim genuine OOS validation or strategy profitability.

## PHASE 60 — PHASE 44–57 CONTINUITY LOCK

- Added `tests/test_phase60_continuity_lock.py` to prevent silent loss of the
  9L/9M handoff and OOS hardening work across checkpoint recovery.
- Verified Phase 44–46 source seams, Phase 47–48 durable journal/discovery
  capture, Phase 50–54 frozen handoff, Phase 55 recertification boundary,
  and Phase 56–57 acquisition/build boundaries.
- Phase 49 remains explicitly `MISSING_GENUINE_ARTIFACT`; its historical
  genuine Binance 9L result/data was not found in accessible project/library
  history and is not reconstructed or fabricated.
- Focused continuity + restored Phase 47/48 + frozen handoff + Phase 56/57:
  **28/28 PASS**.
- `python -m compileall -q core tests scripts`: **PASS**.
- `is_production_ready=False` remains mandatory.

Artifact: `research/results/phase60_continuity_lock.json`
## PHASE 61 — UNIFIED CONTINUITY CHECKPOINT RECONCILIATION

- Reconciled the two later Phase-60 recovery branches into one source-backed
  checkpoint: the full Phase 44–57 continuity lock plus the Phase-60 genuine
  9L admission-readiness audit.
- Preserved Phase 44–46 source seams, restored Phase 47–48 durable journal /
  discovery capture, Phase 50–54 frozen handoff, Phase 55 recertification
  boundary, and Phase 56–57 acquisition/build boundaries.
- Phase 49 remains `MISSING_GENUINE_ARTIFACT`: the original genuine Binance
  9L report/data is not present in accessible project/library evidence and is
  not reconstructed.
- Phase-60 admission readiness remains fail-closed: no genuine 9L report,
  zero eligible findings, zero preregistrations, production-ready false.
- Unified regression: 111/111 focused tests PASS; compileall PASS.
- This checkpoint is a recovery/continuity phase only; it makes no
  profitability or production-readiness claim.

Artifact: `research/results/phase61_unified_continuity.json`

## PHASE 63 — VERIFIED RUNTIME HISTORICAL GAP-RECOVERY WIRING

- Wired the canonical `VerifiedPaperRuntime` / `VerifiedLiveRuntime` to the existing `DeltaHistory.gap_candles()` adapter when no explicit history fetcher is supplied.
- The adapter is lazy: runtime construction performs no network I/O. Recovery requests only the exact candle buckets strictly inside an observed live-feed gap.
- No second historical-data implementation, interpolation, synthetic candle fallback, or legacy ticker transport was introduced.
- Existing explicit `history_fetcher` injection remains authoritative for deterministic/offline tests and venue-specific adapters.
- Focused verified runtime / gap recovery / socket / data-quality / blocker regression: **43/43 PASS**.
- `python -m compileall -q core data tests scripts`: **PASS**.
- Full repository pytest reached **104 PASS** before the preserved historical strategy digest assertion failed: current normalized digest `575cd4c12a2f97d394e02b185e41529d96350c5c3fba834ce4d77df04f6b6e94` versus forensic baseline `9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2`. This is a provenance/recertification blocker and was not repinned or weakened.
- Real Global socket rollover/server-recovery evidence remains externally BLOCKED by the prior DNS/connectivity limitation. No production readiness claim is made.
- `is_production_ready=False` remains mandatory.

## PHASE 164 — INDEPENDENT PATCH VERIFICATION, RUNTIME-BOUNDARY CERTIFICATION & EXECUTION HARDENING

- **Trade Execution-Boundary Hardening**:
  - Validated `@dataclass(slots=True)` on `core/backtesting/trade.py` without obstructive `__post_init__`, preserving unblocked partial instantiation for record stubs and unit fixtures.
  - Implemented `Trade.validate_executable()` and wired it at the execution boundaries: `TradeSimulator.open_trade()` and `BrokerEngine._route()`.
  - Rejection of invalid directions (non-BULLISH/BEARISH), non-finite or non-positive prices/quantities, and negative risk amounts.
  - Directional geometry validation: BULLISH requires `stop_loss <= entry` and `take_profit > entry`; BEARISH requires `stop_loss >= entry` and `take_profit < entry`.
  - TRAILING_STOP strictly enforces non-zero stop distance, positive activation R, positive distance R, and `trailing_enabled=True`.
  - Breakeven economics fixtures preserved (`test_quant_math_11b.py:test_zero_pnl_is_breakeven_economics` passing 100%).
  - `initial_stop_loss` preserved as immutable opening reference while `stop_loss` trails.
  - Preserved distinct semantics of `setup_score` and `confidence` and verified API serialization.
  - Regression suite: `tests/test_trade_boundary_hardening.py` (12 tests, 100% PASS).

- **Backtest Runtime-Boundary Certification**:
  - Replay determinism certified: identical candle streams yield identical trade sequences, exit prices, and PnLs.
  - Conservative intrabar ambiguity policy certified: bar spanning both stop-loss and take-profit executes stop-loss first (`LOSS`, `ambiguous=True`).
  - Position manager precision, notional capping, and dust-rejection certified.
  - Post-cost R:R adverse entry shift certified: erosion below minimum policy fails closed before order construction.
  - Exact net PnL accounting (gross minus commission, slippage, and funding) certified.
  - Trailing stop anchoring to initial stop-loss certified for invariant realized R-multiple calculation.
  - Single-position first-wins idempotency certified.
  - Ledger balance reconciliation against completed trade net PnLs certified.
  - Certification suite: `tests/test_backtest_runtime_boundary_certification.py` (8 tests, 100% PASS).

- **Paper-Runtime Integrity and Recovery**:
  - Sequenced feed consumption and continuous market clock certified.
  - Fail-closed execution under active kill switches or invalid R:R certified.
  - Repaired `PaperTradingEngine._mark_order_filled()`: now properly marks the primary registered order instance `FILLED` in `order_registry` even when trailing-stop promotion copies the order or slippage wrappers adapt it.
  - Unified fill economics to `paper_cost_profile()` (non-zero rate and slippage).
  - Reconciler atomic snapshot journal durability (`persist` / `load_snapshot`) and restart recovery certified.
  - Reconciler fail-closed halt (`MISMATCH`, `halt_new_orders=True`) on position side or quantity divergence certified.
  - Certification suite: `tests/test_paper_runtime_boundary_certification.py` (6 tests, 100% PASS).

- **Full Suite & Blocker Transparency**:
  - Full suite verified: 4,126 passed, 56 skipped, 5 failed (exact 5 deliberate strategy-digest change detectors under `BLOCK-163-01`).
  - `python scripts/generate_manifest.py --root . --verify` -> `MANIFEST_PASS (0 problems)` on 1,966 entries.
  - Strategy status: `EDGE NOT ESTABLISHED`.
  - Production readiness: `NOT_PRODUCTION_READY`.

## PHASE 165 — PROVENANCE RECOVERY, RESEARCH RECERTIFICATION & REMAINING-SYSTEM BUILD

- **Quarantine Dirty Archive**:
  - Located unmanifested secondary archive `QuantEngine_PHASE161_RELEASE_CANDIDATE (2).zip` (61,526,881 bytes, SHA-256 `2a2a5f616d1ae2977cb2479ed6f6336ed5c95823f6247467df1fde1328e37a1b`) containing 966 dirty `*.pyc` files in delivery root.
  - Quarantined to `../QUARANTINE_DIRTY_ARCHIVES/QuantEngine_PHASE161_RELEASE_CANDIDATE (2).zip` outside delivery directory with byte-identical cryptographic verification.

- **Phase 162 Provenance Reconciliation**:
  - Resolved discrepancy between sealed Phase 162 archive reports and post-seal amended working-tree reports.
  - Preserved original sealed copies in `reports/historical_sealed_phase162/` (`PHASE162_RELEASE_GATES_SEALED.json` sha256 `6ec688e8...`, `PHASE162_BLOCKERS_SEALED.json` sha256 `7c4c6578...`).
  - Preserved post-seal corrected copies in `reports/` (`PHASE162_RELEASE_GATES.json` sha256 `f94aff1f...`, `PHASE162_BLOCKERS.json` sha256 `5d053de9...`).
  - Authored `reports/PHASE165_PROVENANCE_ADDENDUM.md` recording downgrade reasons, dates, and test references.

- **Authentic Git Repository History Recovery**:
  - Verified restored `.git` commit database: remote `https://github.com/vishalkharade1-svg/quantengine-spring-41.git`.
  - Reconciled branch lineages: `main` (commit `ffefa14`) and `agents/todo-list-analysis-fix` (commit `699ca76`).
  - Discovered that `main` root `e49f61e` and `699ca76` share identical tree `0d87d721ce3a206ee735502e41476f5809304d9a`.
  - Proved ancestry link: commit `004b2bcbe5f3...` has identical tree `036ba5d2...` to `acab874...` which is an authentic ancestor of `HEAD`.
  - Resolved `BLOCK-163-02` to `VERIFIED_RECOVERED`.

- **Strategy Identity Decoupling Architecture**:
  - Implemented `core/research/strategy_identity.py` and `tests/test_strategy_identity_separation_phase165.py` (4 tests, 100% PASS).
  - Decoupled Alpha Strategy Core (v1.1, 6 files, LF SHA `7cef0d21631b57e15a4c07e41cf6aec8400c4048dd350ed862caf22992fa7d9e`) from Runtime Infrastructure (v1.1, 3 files, LF SHA `d5f9546e0b30b498556b4d0eb58d048e75e9c0a31785bf202ae37f7a599ad3da`).
  - Proved that Phase 164's fix to `paper_trading_engine.py` altered only Runtime Infrastructure while leaving Alpha Strategy Core invariant.
  - Preserved the historical Phase 14 pin `c52e648ca24f...` in the 5 historical change detector tests (`BLOCK-163-01`) intact without fabricating hashes.
  - Authored `reports/PHASE165_STRATEGY_ARCHITECTURE_RECERTIFICATION.md`.

- **Reconciled Test Census & Standing Status**:
  - Authored `reports/PHASE165_TEST_RECONCILIATION.md` explaining the 1-test delta in `test_release_records_phase161.py`.
  - Total collected tests: 4,192 (4,131 passed, 56 skipped, 5 failed).
  - Strategy status: `EDGE NOT ESTABLISHED`.
  - Production readiness: `NOT_PRODUCTION_READY`.

## Phase 166 — Independent Release Verification, Runtime Hardening & Evidence Closure (2026-10-19)

- **Archive Baseline Certified**:
  - Independently verified QuantEngine_PHASE165_RELEASE_CANDIDATE.zip (56,526,188 bytes, sha256 1e595c3b...) against detached record RELEASE_HASH_PHASE165.txt.
  - 1,978 members, 0 CRC errors, 0 credentials, 0 pyc bytecode.

- **Runtime Boundary Certified (97 Tests Green)**:
  - Backtest determinism, intrabar conservative SL priority, accounting & realized R, trade validation, paper trading lifecycle, multi-stream multiplexer, protective bracket simulator, and mobile push gateway all verified green.

- **Strategy Identity Hardening**:
  - Hardened compute_composite_digest in core/research/strategy_identity.py to fail closed on empty, duplicate, traversal, or missing files.
  - Added test_05_fail_closed_validation in tests/test_strategy_identity_separation_phase165.py.

- **Release Records Contract**:
  - Added tests/test_release_records_phase166.py (6/6 PASS).
  - Published reports/PHASE166_INDEPENDENT_VERIFICATION.md, reports/PHASE166_TEST_RESULTS.json, reports/PHASE166_BLOCKERS.json, reports/PHASE166_RELEASE_GATES.json, reports/PHASE166_PROVENANCE.json.

- **Testnet Preflight & Safety Enforced**:
  - Public catalog verified on Delta India Testnet. Authenticated preflight (--dry-run) verified fail-closed abort on 401 Unauthorized when credentials are unset. Zero orders submitted.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

## Phase 167 — Independent Phase 166 Release Audit & Remaining System Completion (2026-10-19)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE166_RELEASE_CANDIDATE.zip` (56,542,973 bytes, sha256 `ec9fac040897da6a324d0eec995cf144feb3b69a5852e8f1bcb207f1ab1991df`) against detached record `RELEASE_HASH_PHASE166.txt`.
  - 1,984 members, 0 CRC errors, 0 credentials, 0 pyc bytecode.

- **Runtime Certification Suite Reproduced (104 Tests Green)**:
  - 104/104 tests passed across backtest boundary, paper runtime boundary, trade hardening, strategy identity, multi-stream multiplexer, protective bracket, mobile gateway, paper trading lifecycle, order executor, authoritative paths, runtime parity, and release records.

- **Forensic Inconsistency Reconciled**:
  - 9-file comparison matrix evaluated across Phase 14 mint commit `3f19895`, current Git commit `ffefa14`, raw disk bytes, and LF-normalized bytes.
  - Proved that exactly 7 of 9 files are identical in Git commit blobs, while 3 files have local modifications in the uncommitted disk working tree, and 3 files have Windows CRLF line endings.
  - Historical hash `c52e648c...` reflects an uncommitted pre-commit-3f19895 working tree on Windows.

- **Strategy Identity Hardening**:
  - Implemented `normalize_rel_path` in `core/research/strategy_identity.py` to enforce non-empty strings, reject whitespace, normalize path separators, reject path traversal (`..`), reject absolute paths, and catch duplicate alias representations (e.g. `./` vs relative or backslashes).
  - Added `test_06_path_normalization_and_collision_handling` to `tests/test_strategy_identity_separation_phase165.py`.

- **Release Records Contract**:
  - Added `tests/test_release_records_phase167.py` (8/8 PASS).
  - Published `reports/PHASE167_INDEPENDENT_AUDIT.md`, `reports/PHASE167_TEST_RESULTS.json`, `reports/PHASE167_BLOCKERS.json`, `reports/PHASE167_RELEASE_GATES.json`, `reports/PHASE167_PROVENANCE.json`.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

## Phase 168 — Execution-Economics Reconciliation, Evidence Integrity & Strategy Historical Reconstruction (2026-10-19)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE167_RELEASE_CANDIDATE.zip` (56,609,904 bytes, sha256 `e0eab8a8f76a000f6d14a95c0975cb974df6aa661346c197ea5ca7bf44e42dcf`) against detached record `RELEASE_HASH_PHASE167.txt`.
  - 1,999 members, 0 CRC errors, 0 credentials, 0 pyc bytecode.

- **Authoritative Ledger & Execution Economics Reconciled**:
  - Captured authoritative venue records: `research/captures/phase168_ledger/` (wallet balances, 100-page wallet transactions, fills, positions).
  - Executed deterministic cross-validation in `scripts/reconcile_phase168_execution_economics.py` and published `reports/PHASE168_EXECUTION_ECONOMICS_RECONCILIATION.md`.
  - Leg 1 Buy fill `363f258b...` commission `-0.04355024 USD` matched wallet commission posting exactly.
  - Leg 2 Sell fill `6dd5caa5...` commission `-0.04355262 USD` matched wallet commission posting exactly.
  - Realized cashflow `+0.00450000 USD` matched wallet realized PnL posting exactly.
  - Net economic impact of `-$0.08260286 USD` matched authoritative equity delta ($198.47068846 -> $198.38808560 USD) to 8 decimal places.
  - Verified account 100% flat (`size = 0, entry_price = None`), 0 open orders.

- **Strategy Historical Identity Reconstructed**:
  - Authored `core/research/historical_reconstruction.py` and published `reports/PHASE168_STRATEGY_HISTORICAL_RECONSTRUCTION.md`.
  - Reconstructed the 9 legacy files across Git commit milestones (`3f19895` mint, `fbeb860` runtime, `ffefa14` HEAD, and uncommitted disk).
  - Maintained the 5 historical change-detector tests as red by contract against `c52e648c...` (`BLOCK-168-01`) without altering pins.

- **Release Records Contract & Testing**:
  - Added `tests/test_strategy_historical_reconstruction_phase168.py` (3/3 PASS).
  - Added `tests/test_release_records_phase168.py` (8/8 PASS).
  - Full certification test suite: 144/144 tests passed with pristine snapshot guard.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

## Phase 169 — Execution Economics Verifier Hardening & Reproducible Release Audit (2026-10-19)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE168_RELEASE_CANDIDATE.zip` (56,650,124 bytes, sha256 `727dd8422a4d220231e742f18c953ac0ca2c1ed3574404ca61c91c4e72a90295`) against detached record `RELEASE_HASH_PHASE168.txt`.
  - 2,017 members and 2,016 manifest entries verified byte-for-byte.

- **Execution Economics Verifier Hardened**:
  - Implemented `core/reconciliation/execution_economics_verifier.py` with six decoupled component verifiers:
    1. *Private WebSocket Fills:* Decodes and validates frame sequence, required schema (`f, s, p, S, r, sy, i, o, c, t, se`), matches fills by stable fill id and microsecond timestamps, cross-verifies side, size, price, symbol, order id, role, and rejects duplicate/malformed frames (4 frames examined, 2 matched, 0 duplicates, 0 rejected).
    2. *Top-of-Book L2 Friction & Quote Binding:* Loads 113 top-of-book L2 samples, aligns to fill timestamps within 208ms/119ms, computes side-aware slippage (0.0 bps on both legs), and distinguishes slippage from limit-price improvement (+8.50 points on Leg 2 favorable crossing).
    3. *Commission Reconciliation & Duplicate Prevention:* Indexes wallet postings with duplicate detection, validates exact REST commission match (`0.04355024 USD` and `0.04355262 USD`), and validates fee decomposition (`base_fee + gst == total_commission`) within 1e-8 tolerance (`0E-8 USD` residual).
    4. *Realized Cashflow Attribution:* Uniquely attributes cashflow matching product `BTCUSD`, position size 1, entry price `82,015.50 USD`, exit price `82,020.00 USD`, and derives gross P&L using contract multiplier `0.001` (`+0.00450000 USD`, 0.0 residual).
    5. *Chronological Ledger Balances:* Pre-experiment balance independently established from preceding transaction `985f902d...` (`198.47068846 USD`), running balances verified across all 3 experiment steps (`198.42713822 -> 198.43163822 -> 198.38808560 USD`), and balance delta compared against expected net P&L with 0.00000000 USD residual.
    6. *Positions & Open Orders:* Positions verified flat (`size = 0` for BTCUSD and ADAUSD), open orders verified 0 via authoritative order/blocked margin (`order_margin == "0"`, `blocked_margin == "0"`) and post-flight experiment cleanup.

- **Regression Suite Authoring**:
  - Created `tests/test_execution_economics_verifier_phase169.py` containing 27 comprehensive regression tests covering all failure modes with clearly labeled synthetic fixtures (27/27 PASSED).

- **Release Records Contract & Testing**:
  - Created `tests/test_release_records_phase169.py` certifying Phase 169 release records, historical pins (Phase 161 through 168), and gate invariants (8/8 PASS).
  - Runtime certification suite: 179/179 tests passed across 18 subsuites.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

### Item 141 (Phase 170 — Independent Phase 169 Audit, Timestamp Provenance & Historical Strategy Lineage, 2026-10-19)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE169_RELEASE_CANDIDATE.zip` (56,688,890 bytes, sha256 `be9b0c0d9f307669a9888690432d0c9dd025dc25919cc9917d4151346971b989`) against detached record `RELEASE_HASH_PHASE169.txt`.
  - 2,030 members and 2,029 manifest entries verified byte-for-byte.

- **Timestamp Provenance Forensics**:
  - Dissected the `1760805669389773 us` apparent 1-year discrepancy: proved mathematically that $1,760,805,669$ is exactly $31,536,000$ seconds (365 days) earlier than $1,792,341,669$ ($2025\text{-}10\text{-}18\text{T}16:41:09\text{Z}$ vs $2026\text{-}10\text{-}18\text{T}16:41:09\text{Z}$). The time 16:41:09 was the timestamp of the prior Phase 167 trade. The discrepancy was an assistant conversational prose error.
  - Raw venue capture bytes in `research/captures/` were verified 100% pristine: `private_ws_frames.json` contains `1792419977351882 us` and `1792419978695455 us` on `2026-10-19T14:26:17-18Z`, matching REST fills with $< 1.0\text{ ms}$ delta.
  - Hardened `ExecutionEconomicsVerifier` with microsecond unit validation (16 digits), UTC epoch year validation (`year == 2026`), cross-leg chronology ($t_{\text{leg1}} < t_{\text{leg2}}$), and premature fee posting rejection.
  - Added 11 focused regression tests in `tests/test_timestamp_provenance_phase170.py` (11/11 PASSED).

- **Offline L2 Execution Replay Simulation**:
  - Developed `core/research/l2_execution_replay.py` and `scripts/run_phase170_l2_replay.py` simulating orders across 1, 5, 10, and 50 contracts against 113 verified L2 frames.
  - Published `research/results/phase170_l2_execution_replay.json`.
  - Documented micro-structure fee drag: taker crossing on minimum-lot contracts cannot generate positive net return under standard fee tiers (`BLOCK-170-05`). Replay does not prove strategy profitability.

- **Historical Strategy Lineage**:
  - Audited `BLOCK-169-01` (`BLOCK-170-01`). Retained the 5 historical change detector tests failing red by contract (`c52e648c...` vs working tree `9c56f3ff...` raw / `ba17582d...` LF canonical). Decoupled versioned identities maintained in `core/research/strategy_identity.py`.

- **Test Suite Accounting**:
  - Total tests passed: 225 (179 runtime + 27 verifier + 11 timestamp + 8 release contract).
  - Historical change detectors: 5 failing expected (`BLOCK-170-01`). Zero regressions.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

### Item 142 (Phase 171 — Passive Maker Execution, Friction Mitigation & Decision Gating, 2026-10-20)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE170_RELEASE_CANDIDATE.zip` (56,729,831 bytes, sha256 `ae8033a740da52d9fd4dd4799a3ef69a0fd0e862112b232d247e654f9ed2ac3b`) against detached record `RELEASE_HASH_PHASE170.txt`.
  - 2,046 members and 2,045 manifest entries verified byte-for-byte.

- **Maker Execution Model & Fee Analysis**:
  - Formulated `core/execution/maker_execution_model.py` with Decimal precision fee decomposition (base commission + 18% GST).
  - Proved that passive maker execution cuts round-trip exchange fees from $0.0968\text{ USD}$ ($5.90\text{ bps}$) to $0.0387\text{ USD}$ ($2.36\text{ bps}$), achieving a 60.0% fee reduction and lowering the breakeven hurdle from 96.78 points to 38.71 points on BTCUSD.
  - Modeled institutional liquidity rebate tiers ($-0.01\%$), showing negative fee drag (+0.0209 USD net return on flat scalps).

- **Queue Dynamics & Adverse Selection Research**:
  - Implemented `core/research/queue_dynamics.py` with post-only boundary guards and Poisson queue fill probability modeling.
  - Replayed 113 historical L2 frames from `delta_ob_updates_archive.json`: average top bid depth 1,312.53 contracts, top ask depth 686.10 contracts.
  - Modeled queue wait time (5.00s at 100 contracts ahead, 86.2% fill probability in 10s) and adverse selection drag (2.0 bps / 0.0164 USD), proving a net positive benefit of +0.0309 USD per contract over aggressive crossing.

- **Friction Hurdle Decision Gate**:
  - Implemented `core/execution/friction_hurdle_gate.py` with three automated gates: fee-to-target ratio <= 40%, target >= 2x breakeven points, and post-fee R:R >= 1.25.
  - Certified that sub-50-point scalps are rejected as mathematically unviable under taker execution, while swing targets (> 150 points) pass cleanly.

- **Test Suite Accounting**:
  - Executed 238 tests: 233 passed, 5 failed by contract (`BLOCK-171-01`).
  - Added `tests/test_maker_execution_phase171.py` (8/8 passed) and `tests/test_release_records_phase171.py` (8/8 passed).

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

### Item 143 (Phase 172 — Queue-Aware Paper Execution, Post-Cost Backtesting & Maker Edge Validation, 2026-10-20)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE171_RELEASE_CANDIDATE.zip` (56,761,468 bytes, sha256 `18cbec7a7c891212e0add042e22fef0144293454d06a294a0bc4c00f907b0a39`) against detached record `RELEASE_HASH_PHASE171.txt`.
  - 2,062 members and 2,061 manifest entries verified byte-for-byte with zero mismatches.

- **Queue-Aware Paper Execution State Machine**:
  - Implemented `core/paper_trading/queue_aware_paper_engine.py` modeling the complete deterministic order lifecycle:
    `CREATED -> VALIDATED -> RESTING -> PARTIALLY_FILLED -> FILLED` alongside explicit terminal rejections (`REJECTED_POST_ONLY`, `REJECTED_STALE`, `REJECTED_CONSTRAINTS`).
  - Implemented Conservative (0% cancellation credit), Central (50% credit), and Optimistic (touch fill) queue scenarios.
  - Certified zero live exchange adapter or credential exposure via `assert_no_live_adapter_invocation()`.

- **Asymmetric Fee & Execution Contract Formalization**:
  - Enhanced `core/execution/maker_execution_model.py` with `calculate_asymmetric_round_trip`, `validate_instrument_constraints`, and `FeeScheduleProvenance`.
  - Enforced Decimal arithmetic and exact per-leg fee tiers (Maker entry at 2.36 bps effective, Taker exit at 5.90 bps effective, 18% GST).

- **Granular Queue Metrics Calibration**:
  - Updated `core/research/queue_dynamics.py` with `evaluate_granular_queue_behavior`.
  - Formalized Poisson arrival calibration ($\lambda = 20.0$ contracts/s): separated $P(\text{any fill}) = 86.47\%$ from $P(\text{complete fill}) = 86.20\%$, time to first fill ($5.00$s), time to complete fill ($5.05$s), expected filled quantity ($0.86$ contracts), expiration probability ($13.80\%$), adverse selection ($0.0164$ USD), and unfilled opportunity cost ($0.0207$ USD).
  - Explicitly classified as `SIMULATION_ASSUMPTION` rather than verified fill probability.

- **FrictionHurdleGate Pre-Order Backtester Integration**:
  - Integrated gate into `core/backtesting/post_cost_backtester.py` pre-order dispatch boundary, evaluating fee ratio ($\le 40\%$), breakeven multiple ($\ge 2\times$), and post-fee R:R ($\ge 1.25$).
  - Measured trade selection effects across 6 setups: Taker execution rejects 83.3% of setups (pass rate 16.7%); Maker execution rejects 66.7% of setups (pass rate 33.3%).
  - Proved that maker execution does NOT establish edge for micro-scalps ($\le 50$ points); edge is restricted to structures $\ge 150$ points.

- **Data Lineage & Limitations Disclosed**:
  - Continuous 1m candles verified at exactly 1,440 rows (24h on 2026-09-05/06). High-frequency L2 archive verified at 113 frames.
  - Multi-year 2024–2026 continuous tick depth is unsupplied and recorded as `BLOCKED_EVIDENCE` (`BLOCK-172-05`).

- **Test Suite Accounting & Reconciliation**:
  - Total tests executed: 269.
  - Added `tests/test_maker_execution_phase172.py` (23/23 passed) and `tests/test_release_records_phase172.py` (8/8 passed).
  - Baseline tests: `test_maker_execution_phase171.py` (8/8 passed), `test_upstream_hypothesis_audit.py` (14/14 passed).
  - Reconciled 5 historical change-detector failures (`BLOCK-172-01`) as belonging to distinct collection scopes.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

### Item 144 (Phase 173 — Independent Phase 172 Audit, Queue Model Validation & Post-Cost Result Reproduction, 2026-10-20)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE172_RELEASE_CANDIDATE.zip` (56,809,944 bytes, sha256 `67d3e60e88f21c7c53fd5c0d0b5fbfc7f789df65099fe9636c2b6ffc8d33571c`) against detached record `RELEASE_HASH_PHASE172.txt`.
  - 2,077 members and 2,076 manifest entries verified byte-for-byte with zero mismatches.

- **Independent Reproduction of All Six Setups**:
  - Recalculated all six canonical setups across 5 comparative variants (A through E).
  - Micro-Scalp (4.5 pts), Tight Scalp (15 pts), and Small Intraday (50 pts) fail under all execution styles.
  - Standard Intraday (150 pts): Rejected under Taker (fee ratio 64.6%); passes Rule 1 under Maker (25.8%) but rejected on Rule 3 (post-fee R:R 0.80 < 1.25).
  - Swing Target (400 pts): Passes under Maker (post-fee R:R 1.51 >= 1.25); rejected under Taker (post-fee R:R 1.02 < 1.25).
  - Wide Trend (1000 pts): Passes under both Taker and Maker.

- **Mathematical Derivation of the 150-Point Setup P&L**:
  - Derived why Conservative Maker yields +$0.0519 while Taker yields +$0.0532.
  - Taker round-trip commission is 5.90 bps each leg (0.0968 USD total fee), yielding +$0.0532 USD net with immediate execution and 0 adverse selection.
  - Asymmetric Maker entry (2.36 bps) + Taker exit (5.90 bps) costs 0.0678 USD, saving 0.0290 USD in commission. However, adverse selection post-fill drift (-2.0 bps = -0.0164 USD) and non-fill opportunity cost (13.80% probability = -0.0138 USD) total 0.0302 USD.
  - Because risk drag (0.0302 USD) exceeds commission savings (0.0290 USD), expected net outcome ($0.1500 - 0.0678 - 0.0164 - 0.0138 = +$0.0519 USD) underperforms taker (+0.0532 USD).

- **Queue Dynamics Mathematical Audit**:
  - Proved that the 86.47% (any fill) and 86.20% (complete fill) estimates represent the CDF of an exponential block-waiting model ($1 - \exp(-\lambda t / Q)$).
  - Contrasted with an Erlang-100 Poisson arrival process (> 99.9999% fill probability), proving the model treats queue consumption as a single aggregate hazard event. Formally classified as `SIMULATION_ASSUMPTION`.

- **Friction Hurdle Hierarchy**:
  - Formally proved Rule 1 (fee ratio <= 40%) strictly subsumes Rule 2 (target >= 2x breakeven <=> fee ratio <= 50%).
  - Identified Rule 3 (post-fee R:R >= 1.25) as the active binding constraint on mid-range targets.

- **Data Lineage & Limitations Disclosed**:
  - Confirmed `1m.parquet` (1,440 continuous rows from 2026-09-05/06) and `delta_ob_updates_archive.json` (113 L2 frames from 2026-10-19) represent disjoint observation windows.
  - Multi-year 2024–2026 continuous tick depth is unsupplied and recorded as `BLOCKED_EVIDENCE` (`BLOCK-173-05`).

- **Test Suite Accounting & Reconciliation**:
  - Added `tests/test_phase173_audit.py` (9/9 passed) and `tests/test_release_records_phase173.py` (8/8 passed).
  - Audited `test_maker_execution_phase172.py` (23/23 passed), `test_maker_execution_phase171.py` (8/8 passed), `test_upstream_hypothesis_audit.py` (14/14 passed).
  - Exactly 5 historical change-detector tests fail by contract (`BLOCK-173-01`), preserved red per safety rule #7.

- **Privacy & Security Protection**:
  - Published `reports/PHASE173_PRIVACY_REVIEW.md`. Scoped privacy scan passed with 0 credential leaks and 0 private telemetry exposures.

- **Standing Status**:
  - SYSTEM STATUS: NOT_PRODUCTION_READY.
  - STRATEGY STATUS: EDGE NOT ESTABLISHED.

## Phase 174 — Independent Economics Reconciliation, Gate Integrity & Evidence-Calibrated Execution (2026-10-20)

- **Mandatory Final Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`.
- **Archive Provenance Verified**:
  - `QuantEngine_PHASE172_RELEASE_CANDIDATE.zip` verified against `RELEASE_HASH_PHASE172.txt` (`67d3e60e88f21c7c53fd5c0d0b5fbfc7f789df65099fe9636c2b6ffc8d33571c`).
  - `QuantEngine_PHASE173_RELEASE_CANDIDATE.zip` verified against `RELEASE_HASH_PHASE173.txt` (`db88433208b4059369734c6e6f2e9c7aa1fc7c6193bed93c5d6392e79bae0e8e`).
- **Historical P&L Discrepancies Conclusively Reconciled**:
  - 50-pt setup: Derivation of `-$0.00511580 USD` (Symmetric Maker in JSON) vs `-$0.02480000 USD` (flat $0.0748 allowance in Markdown table).
  - 150-pt setup: Published `+$0.0519 USD` proved as 4-decimal truncation of `+$0.05197530 USD`; standard `ROUND_HALF_UP` yields `+$0.0520 USD`. Proved that $0.01380 USD non-fill drag is a counterfactual benchmark metric, NOT a realized balance debit.
  - 400-pt & 1000-pt setups: Reconciled `+$0.3448 USD` and `+$0.9447 USD` (Symmetric Maker) with `+$0.3017 USD` and `+$0.9016 USD` (Asymmetric + Non-Fill Drag).
- **Friction Hurdle Gate Fortification & Proofs**:
  - Proved Rule 1 ($\text{Fee Ratio} \le 40\%$) strictly subsumes Rule 2 ($\text{Target Multiple} \ge 2.0\times \iff \text{Fee Ratio} \le 50\%$).
  - Fortified `evaluate_friction_hurdle` with safe parsing to fail closed on `None`, `NaN`, `Inf`, negative prices, and non-positive quantities without crashing.
  - Added object-oriented `FrictionHurdleGate` class interface.
- **Queue Dynamics 7-Question Audit**:
  - Formally answered all 7 questions in `reports/PHASE174_QUEUE_MODEL_AUDIT.md`.
  - Proved $86.47\%$ and $86.20\%$ reflect single-event exponential block hazard ($T \sim \text{Exp}(\lambda / Q)$), not an Erlang counting model. Retained strictly as `SIMULATION_ASSUMPTION`.
- **Paper Execution Safety & Live Isolation**:
  - Validated full state transitions and verified that `assert_no_live_adapter_invocation()` passes with zero live adapter calls.
- **Data Coverage & Test Accounting**:
  - Parquet candles (1,440 continuous 1m bars from 2026-09-05/06) and L2 snapshots (113 frames from 2026-10-19) confirmed temporally non-overlapping.
  - Authenticated execution fills stand at $N = 2$ (requiring $N \ge 30$). Proposed future testnet experiment protocol.
  - 5 historical strategy change-detector test failures contractually preserved failing red (`BLOCK-174-01`).
- **Reports Published**:
  - `reports/PHASE174_INDEPENDENT_ECONOMICS_AUDIT.md`
  - `reports/PHASE174_PNL_RECONCILIATION.md`
  - `reports/PHASE174_QUEUE_MODEL_AUDIT.md`
  - `reports/PHASE174_GATE_ENFORCEMENT_AUDIT.md`
  - `reports/PHASE174_DATA_EVIDENCE_AUDIT.md`
  - `reports/PHASE174_PRIVACY_REVIEW.md`
  - `reports/PHASE174_FINDINGS.json`
  - `reports/PHASE174_TEST_RESULTS.json`
  - `reports/PHASE174_BLOCKERS.json`
  - `reports/PHASE174_PROVENANCE.json`
  - `reports/PHASE174_RELEASE_GATES.json`
- **Tests Added**:
  - `tests/test_phase174_economics_reconciliation.py` (10/10 passed)
  - `tests/test_release_records_phase174.py` (8/8 passed)
- **Standing Blockers Carried**: `BLOCK-174-01` through `BLOCK-174-07`.

### Item 146 (Phase 175 — Contract Multiplier, Notional & Fee-Basis Forensic Audit, 2026-10-20)

- **Archive Baseline Certified**:
  - Independently verified `QuantEngine_PHASE174_RELEASE_CANDIDATE.zip` (56,887,608 bytes, sha256 `d0057024557209c57b8f138bf3eb8366b0a55e439924acc56de01f9d1d647307`) against detached record `RELEASE_HASH_PHASE174.txt`.
  - 2,101 members and 2,100 manifest entries verified byte-for-byte with zero mismatches.

- **$42,082 vs $82 Notional Discrepancy Forensically Resolved**:
  - Proved that the published round-trip maker fee of $0.03871580 USD mathematically requires an entry price of $82,000.00 USD (yielding a fee-bearing notional of $82.00000 USD per contract at 0.001 multiplier).
  - Proved that an entry price of $42,082.00 USD yields an entry notional of $42.08200 USD and round-trip maker fees of $0.01987450 USD.
  - Confirmed that all executable code and JSON artifacts strictly use $82,000.00 USD, and that '$42,082.00' was an accidental transcription typo in the narrative table header of the Phase 174 summary for the contemporaneous Level-2 order book ask price ($82,082.50 USD).

- **Contract Specifications Verified**:
  - Authoritatively verified from `data/fixtures/delta/delta_mcp_public_products_20260925.json` that BTCUSD (Product ID 84) is a vanilla linear perpetual futures contract (`notional_type: 'vanilla'`, `is_quanto: false`) with `contract_value: 0.001 BTC`, quoted and settled in USD.
  - Linear P&L payoff: $\text{Gross P\&L} = (P_{\text{exit}} - P_{\text{entry}}) \times M \times Q$.

- **Dimensional & Property Tests**:
  - Proved linear scaling: fee amounts scale strictly proportionally with quantity and entry price.
  - Multiplier (0.001) is applied exactly once to notional.
  - Evaluated and verified all 6 canonical setups across both price regimes ($82,000.00 baseline and $42,082.00 diagnostic hypothesis).

- **Hurdle Gate Subsumption Hierarchy Reaffirmed**:
  - Rule 1 ($\text{Fee Ratio} \le 40\%$) strictly subsumes Rule 2 ($\text{Target Multiple} \ge 2.0\times$). Rule 2 retained for compatibility and diagnostic reporting. Rule 3 is an independent binding constraint.
  - Gate verified to fail closed on all malformed, non-finite, None, and negative inputs.

- **Data Evidence & Bounded Expectancy Scope**:
  - Candle data (September 2026) and L2 updates (October 2026) confirmed non-overlapping disjoint windows.
  - Authenticated execution sample size confirmed at $N=2$.
  - Scoped micro-scalp failure strictly to the tested 2.36 bps cost scenario, distinguishing modeled scenario failure from universal unprofitability.

- **Reports Published**:
  - `reports/PHASE175_INSTRUMENT_ECONOMICS_AUDIT.md`
  - `reports/PHASE175_NOTIONAL_FEE_RECONCILIATION.md`
  - `reports/PHASE175_CANONICAL_PNL_RESULTS.md`
  - `reports/PHASE175_HURDLE_GATE_AUDIT.md`
  - `reports/PHASE175_DATA_EVIDENCE_AUDIT.md`
  - `reports/PHASE175_PRIVACY_REVIEW.md`
  - `reports/PHASE175_FINDINGS.json`
  - `reports/PHASE175_TEST_RESULTS.json`
  - `reports/PHASE175_BLOCKERS.json`
  - `reports/PHASE175_PROVENANCE.json`
  - `reports/PHASE175_RELEASE_GATES.json`

- **Tests Added**:
  - `tests/test_phase175_instrument_economics.py` (10/10 passed)
  - `tests/test_release_records_phase175.py` (8/8 passed)

- **Standing Blockers Carried**: `BLOCK-175-01` through `BLOCK-175-07`.

- **Mandatory Final Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`.



