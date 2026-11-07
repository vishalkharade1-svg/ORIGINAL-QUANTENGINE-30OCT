# Phase153 ledger refresh (EXECUTED read-only, no orders)

- Books verified flat: BTCUSD/ETHUSD/SOLUSD/ADAUSD size 0, 0 open (new keys).
- Fee window extended: 22 fills, commission sum 0.62949307 = −wallet postings exactly. MATCH holds at 2.2x the Phase147 window.
- Funding rows: 0 (no held-through-settlement; старой ADAUSD long is old-account).
- Artifacts: `research/captures/phase153_ledger/` (scanner PASS).
- Release rebuild running in background (foreground 120s timeout hit mid-write; partial 3.2MB discarded by rebuild).
