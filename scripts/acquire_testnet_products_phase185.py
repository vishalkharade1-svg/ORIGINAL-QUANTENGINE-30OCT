import httpx
import json
from pathlib import Path

url = "https://cdn-ind.testnet.deltaex.org/v2/products"
print(f"Querying {url}...")
try:
    resp = httpx.get(url, timeout=10.0)
    print("Status code:", resp.status_code)
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", [])
        print(f"Total products returned: {len(result)}")
        
        perps = [p for p in result if p.get("contract_type") == "perpetual_futures" and p.get("state") == "live"]
        print(f"Live perpetuals count: {len(perps)}")
        
        # Save products catalog snapshot to research/results/phase185_testnet_products_snapshot.json
        output_path = Path("research/results/phase185_testnet_products_snapshot.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Saved {len(result)} products to {output_path}")

        for p in perps[:25]:
            sym = p.get("symbol")
            pid = p.get("id")
            cv = p.get("contract_value")
            tick = p.get("tick_size")
            qa = p.get("quoting_asset", {}).get("symbol") if isinstance(p.get("quoting_asset"), dict) else p.get("quoting_asset")
            sa = p.get("settling_asset", {}).get("symbol") if isinstance(p.get("settling_asset"), dict) else p.get("settling_asset")
            status = p.get("trading_status")
            print(f"Symbol: {sym:<12} ID: {str(pid):<6} Mult: {str(cv):<8} Tick: {str(tick):<8} Quote: {str(qa):<6} Settle: {str(sa):<6} Status: {status}")
except Exception as e:
    print(f"Error querying {url}: {e}")
