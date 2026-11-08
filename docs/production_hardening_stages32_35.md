# QuantEngine Production Hardening — Stages 32–35

**Scope:** additive, offline evidence gates stacked on PR #14 (Stages 28–31). The validators inspect operator-supplied records only; they do not execute strategies, query exchanges, cancel orders, flatten positions, or deploy.

## Stage 32 — Strategy artifact provenance and reproducibility
Pins the source commit, strategy specification, configuration, feature schema, dependency lock, runtime image and final artifact with SHA-256 digests. Requires a fixed seed, at least two matching replay-output digests, an environment fingerprint and independent reproducibility review. The gate does not rebuild the artifact or recompute its hashes.

## Stage 33 — Backtest validity and leakage controls
Requires chronological, non-overlapping train/validation/test windows; purge and embargo windows at least as long as the maximum label horizon; dataset provenance; feature-availability and lookahead attestations; survivorship-bias review; costs/fees inclusion; untouched OOS set; and independent research review. The gate does not inspect raw datasets or prove that OOS data stayed untouched.

## Stage 34 — Execution capacity and economics stress
Requires venue/instrument context, sample window, volume profile, spread/impact models, fee schedule and stress scenarios. Observed participation, spread, slippage and impact must remain within declared limits; capacity breaches and rejected stress scenarios must be zero; performance must include execution costs. Model quality and sample representativeness need independent verification.

## Stage 35 — Runtime containment and kill-switch drills
Requires drills for stale market data, venue disconnect, risk-limit breach, operator kill switch, process crash and clock skew. Detection/containment latency must remain within limits; open orders and residual exposure must be reconciled; restart must require manual re-arm and automatic re-arm must be disabled. The gate does not run drills or actuate a kill switch.

## Safety and release posture
All four stages return `live_arming_permitted=False`. “Evidence complete” means structurally complete, not authenticated. No live execution or deployment is authorized. Earlier blockers remain: Stage 4 canonical ancestry, credential revocation, independent OOS and venue-economics evidence, risk/reward policy reconciliation, and full repository regression.

**Release posture: PAPER ONLY / HOLD / NOT LIVE READY.**
