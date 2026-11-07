# Delta Exchange MCP Contract — Research/Operator Boundary

**Phase:** 22  
**Status:** IMPLEMENTED / TESTED  
**Production execution:** NOT USED

## Authoritative external source

Delta Exchange MCP documentation:

- https://mcp.delta.exchange/docs
- https://mcp.delta.exchange/docs/tools
- https://mcp.delta.exchange/docs/tools/market-data
- https://mcp.delta.exchange/docs/security

The current documented MCP server is `delta-exchange-mcp` v0.7.0 beta. It runs locally as a stdio subprocess. Public market-data tools require no API key. Account tools require a Read Data key. Trading tools require a Trading-permission key and can place real orders; QuantEngine's research adapter explicitly refuses trading authority.

## Allowed QuantEngine use

The adapter in `research/integrations/delta_mcp.py` is limited to:

- non-secret environment selection;
- keyless/public market-data evidence acquisition;
- explicit public-tool allowlisting;
- deterministic provenance classification.

Default environment is `india_testnet`.

## Public tool allowlist

The 14 public tools documented by Delta are pinned as an explicit allowlist:

`get_ticker`, `list_tickers`, `get_product`, `list_products`, `get_orderbook`, `get_recent_trades`, `get_candles`, `get_mark_price_history`, `get_oi_history`, `get_funding_history`, `get_options_chain`, `get_indices`, `get_settlement_prices`, `get_reference_data`.

Tool names are intentionally not inferred from REST endpoint names.

## Safety boundary

QuantEngine does not consume the MCP client configuration from production modules. Credentials remain outside the repository. `DELTA_MCP_MODE=trade` is rejected by the research adapter.

MCP observations do not automatically become production evidence. A captured observation must still satisfy the relevant QuantEngine evidence schema, provenance, integrity, freshness, and gate requirements.

## Current limitation

The execution environment used for this phase cannot resolve external DNS, so `uvx delta-exchange-mcp` could not be installed/launched here. No external observation was fabricated or promoted. The adapter and tests are offline and deterministic.
