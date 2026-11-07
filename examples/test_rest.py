from core.exchanges.delta.delta_rest import DeltaREST

rest = DeltaREST()

payload = rest.get("/v2/products")

products = payload["result"]

print("Searching for ETH products...\n")

count = 0

for product in products:
    symbol = product["symbol"]

    if "ETH" in symbol.upper():
        print(symbol)
        count += 1

        if count >= 50:
            break

rest.client.close()