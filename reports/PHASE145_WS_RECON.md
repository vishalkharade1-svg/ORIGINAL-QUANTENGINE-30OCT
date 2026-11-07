# Phase145 recon attempt + WS finding (EXECUTED)

## Private-WS characterization (read-only, 30s, no orders)

- Auth OK, subscription accepted, 2 protocol frames (`key-auth`, `subscriptions`), 0 `user_trades` while idle. Channel works; emits only on live fill events. Earlier silence is consistent with no-fill runs, not a broken feed.

## Recon execute (BTCUSD, bounded 2x1)

- Leg 1 buy @82413.5 unfilled 20s → cancelled VERIFIED. WS 2 frames, no trades → reconciliation BLOCKED (honest).
- Script then crashed: `capture_authenticated_fills` raised `ValueError` (0/8 recent fills matched BTCUSD; window holds ETHUSD fills). No funds at risk; book verified flat (BTCUSD/ETHUSD size 0, 0 open).
- Fix (`scripts/bounded_testnet_reconciled_experiment.py:266`): catch empty-window ValueError → `rest_fills: 0` + note (mirrors Phase85 probe handling). Dry-run re-verified green. No strategy/digest code touched.

Verdict: read-only finding + operator-script robustness fix. Production FALSE.
