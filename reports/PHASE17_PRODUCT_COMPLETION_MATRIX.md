# PHASE 17 PRODUCT COMPLETION MATRIX

Date: 2026-10-23
Method: every area traced by direct module/file read and function-level grep this session
(no claims carried over from prior-phase narratives without re-reading). Citations are
`file (key symbol, line)` plus test file names actually present under `tests/`.

Scale: REAL = product-side implemented and wired; RESEARCH-LEVEL = research-only modules
(frozen evidence or candidate registry), not a product surface; NEGATIVE-PROOF = the contract
is "must not analyse without data" and absence is the designed behaviour; ABSENT = nothing
found.

| # | Area | Product side | Test side | Status |
|---|------|--------------|-----------|--------|
| 1 | Data ingestion / provider download | core/exchanges/delta/delta_exchange.py (DeltaExchange, L29), delta_history.py (DeltaHistory, L16), delta_rest.py, delta_products.py, delta_auth.py; core/bars/bar_series.py (BarSeries, L18); core/history/history_database.py; core/universe/history_provider.py (DeltaHistoryProvider, L48) | test_delta_exchange.py, test_delta_history.py, test_delta_loader.py, test_delta_rest_9s.py, test_history_database.py, test_provider_plumbing_9pd.py | REAL |
| 2 | Dataset assembly | core/research/dataset/dataset.py (ResearchDataset, L32), collectors.py, row.py, queries.py; core/research/acquisition/accumulator.py (validate_batch L61, accumulate L104), multi_symbol.py, provenance.py | test_phase32_acquisition_accumulator.py, test_phase37_multi_symbol_acquisition.py, test_phase158_dataset_reconstruction.py; no direct unit test of ResearchDataset class itself found | REAL (acquisition paths); test-side PARTIAL for dataset.py direct import |
| 3 | Feature engineering | core/research/features/indicators.py (bollinger_position L86, obv L105); confluence_features.py (wyckoff_phase L74, fibonacci_zone L242, volume_profile L271, footprint_flow L278 — deliberately UNAVAILABLE without order-flow data, module docstring lines 13/24/31); feature_snapshot.py, causal_window.py | test_research_features_9f.py, test_feature_causality_9r.py, test_phase11f_features.py (incl. test_footprint_and_volume_profile_always_unavailable L255) | REAL (incl. negative proofs) |
| 4 | Strategy representation + canonical setup identity | core/setup/trade_setup.py (TradeSetup, L15), setup_candidate.py (SetupCandidate, L14), trade_setup_builder.py, trade_setup_registry.py; core/identity/instrument_identity.py (build_setup_identity L43, split_setup_identity L96); core/research/strategy_identity.py (compute_composite_digest L91) | test_setup_decision_contract.py, test_trade_setup_builder.py, test_strategy_identity_separation_phase165.py, test_phase64_strategy_recertification.py | REAL |
| 5 | Decision engine + 1:6 RR gate | core/setup/decision_engine.py (DecisionEngine L32, analyze L74); NOTE: 1:6 is the frozen RESEARCH note (L48) while the runtime contract is TradingPolicy risk_reward_allowed 1:1..1:20 (core/risk/trading_policy.py DEFAULT_MAX_RR=20.0 L26, caps L61-63); the 1:6 hard authority lives in the research/decision canon and the 1:20 clamp in policy | test_setup_decision_contract.py, test_hardening_stage123.py, test_level4_rr_exit_policy.py, test_trading_policy.py | REAL (policy+engine); the "1:6 gate" is documented-research authority, runtime enforces 1:20 cap — see REPAIR note D-17-01/R-04 |
| 6 | Risk engine: gates, sizing, stop validation | core/risk/risk_engine.py (loss_limit_blocked L66, kill_switch_active L132, RiskEngine L156), position_sizer.py, conservative_gates.py, market_data_gate.py, contract_gate.py, account.py, portfolio_risk.py | test_risk_gates_12.py, test_position_sizer.py, test_position_sizing_9q.py, test_conservative_risk_gates_phase7.py, test_phase179_risk_enforcement.py, test_portfolio_risk_core.py | REAL |
| 7 | Backtester execution model | backtesting/backtester.py (Backtester L43); core/backtesting/trade_simulator.py (TradeSimulator L28), post_cost_backtester.py, trade_registry.py | test_backtester.py, test_backtester_hardening.py, test_backtester_breakout.py, test_trade_simulator.py, test_simulator_post_cost_gate_13.py | REAL |
| 8 | Accounting | core/backtesting/accounting.py (net_pnl L85, realized_rr L113, realized_r L106, directional_geometry_ok L150, risk_reward_allowed L186, order_rr L212) | test_accounting_9q.py, test_account_profit_factor_9pb.py | REAL |
| 9 | Paper trading engine | core/paper_trading/paper_trading_engine.py (PaperTradingEngine L80, _SlippageAdjustedOrder L60), queue_aware_paper_engine.py, readiness.py | test_paper_trading.py, test_paper_lifecycle_real_10.py, test_paper_main_runtime.py, test_paper_readiness_phase9.py | REAL |
| 10 | Research journal / phase registry | core/research/journal/research_journal.py (ResearchJournal L98), setup_record.py, trade_record.py, journal_query.py, research_repository.py; research/phase11f/candidates.py (SweepReversal L73, WyckoffSpring L186, BreakerRetest L307, RangeRSIFade L471) | test_research_journal_9a.py, test_phase47_journal_persistence.py, test_phase11f_contracts.py, test_phase11f_results.py, test_phase11f_seal.py | REAL |
| 11 | OOS validation methodology | core/research/oos_validation/periods.py (validate_freshness L37, split_bars L59), execution.py (run_frozen_oos L63, load_verified_funding_schedule L39); core/research/oos/validator.py, engine.py | test_oos_validation_18.py, test_phase30_oos_evidence.py, test_oos_execution_readiness.py | REAL (methodology; OOS data corpus itself remains NOT VERIFIED per P104/P192 posture) |
| 12 | Multiple-testing hypothesis control | core/research/regime/multiple_testing.py (sidak_alpha L35, multiple_testing_summary L47); core/research/oos/aggregator.py; core/research/researcher/evaluate.py | test_researcher_15.py (frozen-cleanliness rests + Settings import L498), test_researcher_9k.py (test_sidak_math L948), test_researcher_9m.py (test_sidak_single L259), test_phase11f_multiple_testing.py | REAL |
| 13 | Execution safety gates / ack truth | core/execution/execution_engine.py (ExecutionEngine L70, pending_direction_capacity L56), order_ack.py (AckResult L205, classify_ack L246, classify_exception L345), live_safety_gate.py (LiveSafetyGate.decide L304, require L393), testnet_safety_gate.py (TestnetSafetyGate.evaluate L130) | test_execution_engine.py, test_execution_ack_12.py, test_live_block_11.py, test_contract_gate_13.py, test_phase193a_execution_safety_gate.py, test_phase188_gated_execution_mock.py | REAL |
| 14 | Restart / websocket / order longevity | core/runtime/realtime_engine.py, lifecycle.py, multi_stream_multiplexer.py (get_candles L130), verified_runtime.py (VerifiedPaperRuntime L143, VerifiedLiveRuntime L162); core/live/broker_engine.py, reconciler.py | test_multi_stream_multiplexer_phase163.py, test_phase191_crash_recovery.py, test_phase190_capture_recovery.py, test_reconciler_snapshot_durability_phase7.py, test_verified_runtime_parity_phase4.py, test_realtime.py | REAL |
| 15 | Config validation gates | config/settings.py (Settings L31, _env_float L11, _env_int L21, credential posture block L38-69), config/risk_settings.py, trading_profile.py; core/validation/ is strategy-stats validation (WalkForwardTester L85, MonteCarloSimulator L87, StrategyOptimizer L58) — NOT config validation | test_settings_9q.py, test_risk_settings.py, test_trading_profile.py, test_open_blockers_phase3.py | PARTIAL: env loader present; validation module is misnamed for its role; no dedicated validate_config symbol found |
| 16 | Release packaging + security scan | scripts/generate_manifest.py (package_files L60, generate L133, verify L138, is_secret_bearing_name L88); scripts/security/scan_secrets.py (scan_worktree L103, scan_staged L126, scan_env_history L164) | test_release_manifest_phase154.py, test_secret_scan_phase0.py, test_secret_scan_phase193b.py, test_packaging_no_secrets_phase132.py, test_release_records_phase161.py | REAL (re-verified live this session: manifest 2367 PASS pre-appends; scanner rc=1 fail-closed) |
| 17 | Monitoring / reconciliation | core/monitoring/service.py (start_api L68, run_paper_with_monitoring L239), api_server.py; core/reconciliation/execution_economics_verifier.py; core/live/reconciler.py | test_monitoring_service_9pf.py, test_api_server_9pf.py, test_execution_economics_verifier_phase169.py, test_reconciliation_local_phase5.py, test_reconciliation_adversarial_13.py | REAL |
| 18 | Indicator roster | core/indicators/: adx.py, atr.py, ema.py, rsi.py, sma.py + indicator.py, indicator_engine.py, indicator_cache.py | test_indicator_contract.py, test_indicator_engine.py, test_atr_wilder_9q.py | REAL for the five implemented; see roster notes below |

## Indicator roster detail for area 18 (explicit gaps)

Implemented in core/indicators/: ADX, ATR, EMA, RSI, SMA (+ engine + cache).
Existing adjacent modules and their true status:

- Volume profile: core/volume_profile/ (VolumeProfile, VolumeNode, profile_engine.py,
  profile_registry.py) EXISTS as a product module, but the confluence feature layer
  returns None by design (confluence_features.py volume_profile L271; negative proof test
  test_volume_profile_footprint_registered_none at tests/test_research_features_9f.py L326).
  No dedicated functional test of the engine itself was found. Status: module present,
  integration NEGATIVE-PROOF, tests ABSENT for engine internals.
- Footprint charts: core/orderflow/footprint.py, footprint_registry.py, price_ladder.py
  exist; feature layer deliberately UNAVAILABLE (confluence_features.py footprint_flow L278).
  Status: PARTIAL (module present, feature contract is "must not invent without data").
- Order flow imbalance: no symbol named OFI/imbalance found in a quick sweep; core/orderflow/
  delta.py and delta_engine.py exist (semantics not audited this phase). Status:
  PARTIAL-unverified; tests ABSENT for an explicit OFI.
- Market structure: core/market_structure/ (structure_engine.py, swing_engine.py,
  bos_engine.py, choch_engine.py) with tests (market_structure_contract, causality phase3,
  swing_engine). Status: REAL.
- Wyckoff: research-layer only — confluence_features.py wyckoff_phase L74;
  core/research/regime/indicators.py L265; strategy-candidate WyckoffSpring in
  research/phase11f/candidates.py L186. No core/indicators module. Status: RESEARCH-LEVEL.
- Fibonacci: research/frozen-candidate only (research docs; phase11g_f strand). No
  core/indicators module. Status: RESEARCH-LEVEL.
- VWAP: no indicator module; only a data field (core/bars/bar.py L37, core/indicator_state.py
  L40). Status: ABSENT.
- Bollinger: research-layer only (core/research/features/indicators.py bollinger_position L86,
  tested in test_research_features_9f.py). Status: RESEARCH-LEVEL.
- OBV: research-layer only (core/research/features/indicators.py obv L105, same test file).
  Status: RESEARCH-LEVEL.

## Honest gaps worth the owner's attention (not new claims)

- G1: `config validation` (area 15) is loader-level only; no fail-closed full-config
  validation entry point was found.
- G2: volume-profile engine internals have no functional test (only the negative
  integration proof).
- G3: order-flow imbalance has no explicit, tested implementation (delta engine exists;
  semantics unverified this phase).
- G4: the runtime RR authority is a 1:20 clamp (TradingPolicy), while the documented
  research authority is 1:6; the hard battery (tests/file battery this phase) enforces
  1:6 where the research canon faces risk per-file — reconciliation of these two authorities
  stays an OWNER-LEVEL decision, not something to change autonomously.

## Conclusion for the matrix

No area is a phantom: 14 of 18 areas are product-REAL with tests; the remaining four are
honest partials (dataset.py direct test; config validation entry point; volume profile
engine tests; order-flow imbalance) — none of them breaks a shipped gate by itself.
Area 18's roster gaps (VWAP, Wyckoff, Fibonacci, Bollinger, OBV at product level,
OFI) stand as documented in the phase 16/17 records; adding them is PRODUCT work with
no census impact, and any such work returns first to the owner letterbox because the
census freeze (research/ tracks modified) must be resolved before component work is
permitted to proceed in the same tree.

## Phase 24 update (2026-10-28) — verified-transport replay & paper-session readiness

Additive update to the matrix (no historical row rewritten). New product
surfaces delivered and verified in Phase 24:

| # | Capability | Product side | Test side | Status |
|---|------------|--------------|-----------|--------|
| 24.1 | Verified public-candle transport seam (paper path) | data/realtime/verified_transport.py (`VerifiedPublicCandleTransport`, L66; `notify_down` teardown P24-1 fix, L123; `repair_gap_history`, L188) bound opt-in via QE_PAPER_VERIFIED_TRANSPORT in core/runtime/paper_main.py (L413-435) | tests/test_verified_public_candle_transport.py (11/11), tests/test_verified_paper_engine_integration_23.py (4/4) | REAL |
| 24.2 | Deterministic replay harness over the real assembly | data/realtime/verified_replay.py (`VerifiedTransportReplay` L482+, `ReplayReport`, `reconcile_paper_ledger`, `load_capture`, `synthetic_candle_frames`); operator CLI scripts/run_verified_transport_replay.py (replay-capture / soak / --repair-gap) | tests/test_verified_transport_replay_phase24.py (35/35); sample reports reports/PHASE24_REPLAY_EXAMPLE/*.json | REAL |
| 24.3 | Paper-session operations (runbook + readiness) | docs/operations/PAPER_SESSION_RUNBOOK_PHASE24.md; docs/operations/TESTNET_READINESS_CHECKLIST_PHASE24.md; reports/PHASE24_BLOCKER_REGISTER.md | operationally evidenced by the soak/capture artifacts (EXIT=0) | REAL (paper); testnet NOT AUTHORIZED (owner prerequisites open) |

Mechanical proof from the artifacts: 12,000-frame deterministic soak routed
11,999/11,999 closed candles with zero route errors and an exactly
reconciled paper ledger; disconnect recovery restores LIVE delivery without
duplicate fills; continuity gaps block all closes until an exact repair;
the frozen 1:6 era gate and the runtime policy floor are enforced in the
real chain. Evidence classes stay explicit (CAPTURED vs labelled
SYNTHETIC_FIXTURE). No gate changed.
