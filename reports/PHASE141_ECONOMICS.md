# Phase141 execution economics (EXECUTED read-only, ETHUSD, 8 fills)

Source: `/v2/fills` reload + `/v2/products` fee schedule (quoted taker 0.0005 / maker 0.0002, cval 0.01). No orders placed in this phase.

## Realized vs quoted (all 8 fills)

- 7 taker fills @ **5.310bp** effective vs 5.0bp quoted (+6.2%).
- 1 maker fill @ **2.124bp** vs 2.0bp quoted (+6.2%).
- Uniform +6.2% residual across sides/symbols; matches Phase117 BTCUSD finding (5.310/2.124bp). Cause undetermined — reported, not explained. No venue-fee invention.

## Round-trip nets (gross − fees, quote USD)

- 2438.95→2437.8: gross -0.0115, fees 0.02590, **net -0.03740**
- 2438.35→2438.35: gross 0.0, fees 0.01813, **net -0.01813**
- 2436.40→2436.20: gross +0.002, fees 0.02587, **net -0.02387**
- 2438.25→2437.15: gross +0.011, fees 0.02589, **net -0.01489**

Fees dominate penny-scale moves at 1 contract — no edge claimed (EDGE NOT ESTABLISHED). Funding: positions held seconds–minutes, no settlement events observed; funding leg remains BLOCKED (needs held-through-settlement evidence).

Verdict: TESTNET_EVIDENCE for taker/maker realization; certification still BLOCKED (funding, simultaneous friction binding, WS match).
