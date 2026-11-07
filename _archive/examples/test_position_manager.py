from execution.position_manager import PositionManager
from execution.order import Order


manager = PositionManager()


order = Order(

    symbol="BTCUSDT",

    side="BUY",

    quantity=2,

    entry=64000,

    stop_loss=63900,

    take_profit=64200,

    strategy="ICT",

)


position = manager.open_position(order)


print()

print("OPEN POSITION")

print("=" * 50)

print(position)



manager.update_price(

    "BTCUSDT",

    64100

)


print()

print("AFTER PRICE UPDATE")

print("=" * 50)

print(manager.get("BTCUSDT"))



manager.update_price(

    "BTCUSDT",

    64200

)


print()

print("AFTER TAKE PROFIT")

print("=" * 50)

print(manager.get("BTCUSDT"))