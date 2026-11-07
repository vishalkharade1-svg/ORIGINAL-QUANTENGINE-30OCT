# 11G-G preregistration note (no new hypotheses)

The experiment family is EXACTLY the frozen 11G-F registry
(`research/phase11g_f/hypotheses/hypotheses.json`, sha256
`6181496e2551fc5a`, verified in `freeze_manifest.json` below).
No hypothesis is copied, renamed, redefined, or re-parameterized here;
`hypotheses/` contains this pointer by design so that any divergence
would be a visible new file, not a silent edit.

Frozen by reference: 8 hypotheses H11GF-001…008, NBO family, CLASS-A
params, A/B/C/D costs, risk 2000/0.01/10×/500, 11 preregistered
ablations, N=8/Bonferroni 0.00625, evidence minima 30/3/2/3.
Execution change vs 11G-F: NONE (same NBO channel, same cold-start
folds, same train-only fits). Only the dataset is new (Tier-1 gap).
