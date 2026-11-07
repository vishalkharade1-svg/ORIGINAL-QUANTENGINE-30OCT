# PHASE 18 PRODUCT GAP PLAN (12 capabilities, evidence-classified)
Date: 2026-10-23
Basis: this phase's runtime integration trace (file:line citations below; phase 17 matrix used as the
starting inventory). NOTHING here is a profitability or live-readiness claim.

## Verification classes used
VERIFIED = the complete call path exists in the runtime, with tests covering the path.
PARTIAL = path exists but a named link is missing.
ABSENT = no runtime path found.
DESIGNED-NEGATIVE = absence is the documented, deliberately enforced behavior.
NOT VERIFIED = cannot be confirmed from this evidence session.

## Capability table

| # | capability | class | decisive evidence (file:line) |
|---|------------|-------|-------------------------------|
| 1 | startup + config validation | VERIFIED | main.py:92-113 (ExecutionMode.resolve + LiveSafetyGate.require/decide, fail-closed banner); config/settings.py:11-28 (env parse raises on bad values); settings.py:75-81 unknown mode refused fail-closed; paper_main.py:80-102 operator-threshold fail-fast; tests: test_settings_9q.py, test_live_block_11.py:508+, test_paper_main_runtime.py |
| 2 | exchange data + closed-candle integrity | PARTIAL | realtime_engine.py:267 → subscription_manager.py:92,290 → stream_worker.py:185-220 → candle_router.py:62-67 (closed-only routing); missing link: NO transport wired by default (subscription_manager.py:46-69 fail-closed _AuthoritativeCandleTransportRequired; delta_subscription_stream.py:442-458 gap repair NOT_IMPLEMENTED); multi_stream_multiplexer.py:130 has no core importer |
| 3 | normalization/timestamps/continuity/reconnect | PARTIAL | common/timestamp.py normalize_timestamp used at delta_subscription_stream.py:428; candle_finality.py:51 causal finality; reconnect_policy.py:10-31 + stream_worker.py:247-274; missing: BarSeries copy note: missing: BarSeries/history_database gap-continuity NOT attached to the runtime pipeline (replay/examples only); transport gap registry lacks repair (delta_subscription_stream.py:448-457) |
| 4 | feature calculation + strategy integration | VERIFIED | symbol_pipeline.py:46-55,131,140 default_world_factory → institutional_pipeline.py:86-96 IndicatorEngine(EMA/ATR/ADX/RSI); fed on every closed candle via paper_runtime.py:101-107 run_candle; tests: test_institutional_pipeline.py, test_pipeline_runner.py, test_paper_main_runtime.py |
| 5 | order-flow/footprint/volume-profile integration | ABSENT (runtime) | pipeline_context.py:179-181,352-356 footprint/VP/price-ladder fields never populated; price_ladder_stage.py:26-55 built but NOT registered in institutional_pipeline.py:107-125 (no stage registration); footprint.py / profile_engine.py reachable only from tests |
| 6 | strategy signal construction + 1:6 rejection | VERIFIED (gate) / 1:6=DESIGNED-NEGATIVE in runtime | decision_engine.py:74-279 gates; RR rejection at :204-207; priority 700 in pipeline (institutional_pipeline.py:123); runtime policy risk_reward_allowed (accounting.py:186) with TradingPolicy min 1:1–max 1:20 (trading_policy.py:25-26,59-64); MIN_RISK_REWARD=6.0 stays research-frozen (risk_settings.py:454-461, trading_profile.py:8); tests: test_hardening_stage123.py:130-133 |
| 7 | risk limits + position sizing | VERIFIED | risk_engine.py:213 kill switch; :237-246 loss-limit windows; :269-297 pending/direction caps; :427-443 geometry; :444-454 RR; :478-489 exposure; PositionSizer wiring at :170,:491-514; broker gates broker_engine.py:643-657, :704-712, :737-767; tests: test_position_manager.py, test_conservative_risk_gates_phase7.py |
| 8 | paper execution, costs, order lifecycle | PARTIAL | broker_engine.py:812-862 calls TradeSimulator with paper_cost_profile; post-cost R:R gate inside trade_simulator.py:118-184, net pnl :380-391; QueueAwarePaperExecutionEngine (queue_aware_paper_engine.py:143, friction gate :708-762) reachable ONLY via phase-185 experiment script — missing link: not constructed by PaperExecutionAdapter / build_paper_engine |
| 9 | reconciliation/monitoring/fault handling/recovery | VERIFIED | main.py:180-192 wires Reconciler into BrokerEngine (live path); broker_engine.py:533 startup_check, :1155 runtime_check, halts :579-582/:938/:1023/:1064/:1361; monitoring service.py:68-110 start_api, :183-191 remote gateway; lifecycle.py:198-391 restart/pause own-loop; tests: test_lifecycle_9pf.py:130, test_reconciler_snapshot_durability_phase7.py, test_monitoring_service_9pf.py |
| 10 | testnet/live authorization + exchange-write boundaries | VERIFIED | main.py:102-114 LIVE gate; order_executor.py:193-225 requires safety + minted authority; delta_exchange.py:122-131 independent require_write_authority re-verify; sandbox resolution delta_environments.py:78-197 fail-closed; TestnetSafetyGate 16 prereqs testnet_safety_gate.py:113-161; paper stays dry_run=True (paper_runtime.py:77); tests: test_live_block_11.py, test_phase193a_execution_safety_gate.py, test_delta_sandbox_environment_15.py |
| 11 | authenticated mobile/control API | VERIFIED (opt-in) | api_server.py:934 ControlApiServer; all non-shell routes constant-time bearer auth (_authorized :839-855, _dispatch :866-869); POST /control PAPER-only allowlist (header :23-33; _assert_paper_capable tests test_api_server_9pf.py:369-398); remote gateway per-role tokens + TLS fail-closed remote/gateway.py:106-130, :555-581; service.py:55-89 opt-in |
| 12 | reproducible research + leakage controls | VERIFIED (harness) | walk_forward.py:89-253; oos/period.py outcome_leakage authority; leakage-enforcing tests: test_walk_forward_9r.py:22-75, test_feature_causality_9r.py:77-84, test_research_ml_9g.py:143-178, test_quant_math_11b.py:805-916; WalkForwardTester not invoked by runners/scripts (tests/examples only) |

## The smallest engineering milestones to make this a reliable research + paper product

(The ordering is dependency-first; all are OWNER-APPROVABLE product work, none affects shipped
gates; each has a natural verification test.)

- M-01 (Research productization — closes #12 runner gap): add a runner CLI/script that invokes
  WalkForwardTester + OOS validator end-to-end on a declared dataset corpus, emitting a checksummed
  results artifact. Verification: a reproducibility test asserting identical output digests across
  two runs on a fixed fixture.
- M-02 (Transport wiring — closes #2): inject the verified Delta candle transport into
  SubscriptionManager's default factory behind the existing evidence gate, plus a config gate that
  REQUIRES the evidence bundle on boot. Verification: a runtime smoke test asserting closed candles
  reach the pipeline from the sandbox feed (offline harness provided by transcripts; no live
  exchange contact).
- M-03 (Continuity loop — closes #3): attach the HistoryDatabase/BarSeries gap-repair cycle to the
  pipeline (the delta_subscription_stream gap registry at :448-457 gets its repair implemented).
  Verification: a continuity test that drops/fakes N candles in a replay stream and asserts the
  pipeline repair fills them consistently.
- M-04 (Order-flow stage registration — closes #5): register PriceLadderStage inside
  InstitutionalPipeline's stage chain (behind a config gate), and populate
  pipeline_context.footprint/volume_profile/price_ladder fields from the stage. Verification: a
  pipeline test asserting the context fields are populated for a replayed order-flow dataset, and
  that a config gate still produces UNAVAILABLE semantics when order-flow data is NOT provided.
- M-05 (Queue-aware paper path — closes #8): construct QueueAwarePaperExecutionEngine from
  PaperExecutionAdapter, and route the paper fills through the friction gate (:708-762).
  Verification: a lifecycle test of order latency/queue-position on a mock exchange timeline.
- M-06 (1:6 authority reconciliation — closes #6 policy debt): owner decision to either (a) retain
  the runtime 1:20 TradingPolicy while declaring the research 1:6 as research-canon (CURRENT
  DESIGN), or (b) raise the runtime min-RR to 1:6 on the PAPER path. Each choice needs ONE test
  pinning the chosen semantics (the current repo tests pin (a); keep).
- M-07 (Exposure improvements, no product-blocker): the VolumeProfile engine currently has no
  functional test; add one; OFI (order-flow imbalance) has no implemented symbol; only attempt
  AFTER M-04's stage registration lands.
- M-08 (Live-writer boundary certification): the FIRST live-trade sell/buy seam in
  broker_engine.py:879+ stays UNEXERCISED by design until testnet authorization exists; add a
  DESIGNED-NEGATIVE test asserting paper-only mode never executes that seam; tie it into the
  existing fail-closed test set.

## Honest blockage notes

- All of M-01..M-08 are product engineering; they do NOT require the lineage decision, but they DO
  require a green, stable test tree to avoid interleaving produces-notes with research fixes.
  Milestones are stated so each carries independent verification evidence.
- The 1:6 'gate' in the shipped research canon vs the runtime TradingPolicy max 1:20 remains a
  POLICY question (M-06), deliberately flagged and NOT changed by the agent (owner letterboxed).
- No profitability, no live-readiness, no testnet claim is made anywhere in this file.
