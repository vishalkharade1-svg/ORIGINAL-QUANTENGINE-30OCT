"""
====================================================

Delta Order Executor (Dry-Run)

Maps a risk-validated OrderIntent into a Delta /v2/orders
payload WITHOUT placing a real order. The same payload is
handed to DeltaExchange.place_order() in paper/live mode;
set DELTA_EXECUTE=1 (and DELTA_API_KEY / DELTA_API_SECRET
in .env) to actually place it.

Flow being demonstrated:

    RiskEngine -> context.order (OrderIntent)
        -> DeltaOrderExecutor.build_payload(intent, contract)
        -> DeltaExchange.place_order(payload)

====================================================
"""

import os

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.exchanges.delta.delta_exchange import DeltaExchange
from core.execution.order_executor import DeltaOrderExecutor
from core.risk.order_intent import OrderIntent


def main():

    # -------------------------------------------------
    # Contract (a live caller would use
    # DeltaContractLoader().load().get("BTCUSDT")); the
    # registry carries the Delta product_id + precision.
    # -------------------------------------------------

    registry = ContractRegistry()

    registry.add(
        DeltaContract(
            symbol="BTCUSDT",
            exchange="DELTA",
            contract_type="perpetual_futures",
            tick_size=0.01,
            quantity_step=0.001,
            min_quantity=0.00001,
            max_leverage=100.0,
            maker_fee=0.0005,
            taker_fee=0.001,
            price_precision=2,
            quantity_precision=3,
            product_id=2,
        )
    )

    # -------------------------------------------------
    # Risk-validated OrderIntent (RiskEngine output)
    # -------------------------------------------------

    intent = OrderIntent(
        direction="BULLISH",
        entry=80000.00,
        stop_loss=79500.00,
        take_profit=81000.00,
        risk_reward=2.0,
        quantity=0.062,
        risk_percent=1.0,
        risk_amount=5.00,
        expected_loss=31.00,
        expected_profit=62.00,
        position_value=4960.0,
        leverage=1.0,
        commission=0.0,
        slippage=0.0,
        confidence=64.0,
        score=71.0,
        symbol="BTCUSDT",
        timeframe="1m",
        valid=True,
        reason="accepted by risk engine",
    )

    executor = DeltaOrderExecutor(
        exchange=DeltaExchange(),
        registry=registry,
    )

    contract = registry.get(intent.symbol)

    payload = executor.build_payload(intent, contract)

    print()
    print("=" * 60)
    print("DELTA /v2/orders PAYLOAD (dry-run)")
    print("=" * 60)

    for key, value in payload.items():
        print(f"{key:32}: {value}")

    print()
    print("=" * 60)
    print("EXECUTION")
    print("=" * 60)

    if os.getenv("DELTA_EXECUTE", "0") == "1":

        # Phase 11A: real placement requires the centralized
        # gate (mode == LIVE, ALLOW_LIVE, LIVE_EXECUTE,
        # credentials). Refuses with LiveBlockedError --
        # zero transport calls -- unless fully armed.
        from core.execution.live_safety_gate import LiveSafetyGate

        _gate_inputs = LiveSafetyGate.from_settings(mode="LIVE")

        _safety = LiveSafetyGate.require(
            component="examples.test_delta_order_executor",
            **_gate_inputs,
        )

        print(executor.execute(intent, safety=_safety))

    else:

        print(
            "Dry-run: set DELTA_EXECUTE=1 and keys in .env "
            "to place this order."
        )


if __name__ == "__main__":

    main()