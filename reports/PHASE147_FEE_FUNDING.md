# Phase147 fee-window + funding evidence (EXECUTED read-only, no orders)

Artifacts: `research/captures/phase147_ledger/fills_100.json` (c622c202f6a3, 20226 B), `wallet_100.json` (5aa666cb4d82, 7027 B). Scanner-clean, no secrets.

## Fee window (MATCHED)

- 10 fills (8 ETHUSD + 2 BTCUSD), commission sum 0.13082786.
- Wallet: 10 `commission` postings summing -0.13082786. **Exact match** (fills ↔ ledger).
- Plus 4 `cashflow` (realized-PnL settlements) + 1 `external_deposit` (account funding). No other types.

## Funding (negative evidence, honest)

- Zero standalone funding rows in 15 wallet txns (`fund_id` fields are not funding payments). Positions this session held seconds–minutes, never through a settlement timestamp. Funding leg remains BLOCKED by design, not by omission.

## Certification delta

- Fees: quoted→realized (+6.2% residual, Phase141) now backed by a matched 10/10 ledger window. Fee-history leg substantially CLOSED for this window.
- Still open: funding-through-settlement capture, repeated WS-match robustness, full-suite green.

Verdict: TESTNET_EVIDENCE. Production FALSE.
