# Phase155 — MCP configuration restored (operator-provided)

## Resolution

Phase154 correctly refused to fabricate `.vscode/mcp.json` because no
authentic copy existed in any archive or the worktree, and left the five
`TestMcpConfigTestnetSafe` tests failing as honest evidence. The operator
has now supplied the authentic configuration, so the contract can be
satisfied without invention.

File restored verbatim as `.vscode/mcp.json`:

```json
{
  "servers": {
    "delta-exchange-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["delta-exchange-mcp"],
      "env": { "DELTA_MCP_ENV": "india_testnet" }
    }
  }
}
```

## Contract check (`tests/test_delta_mcp_config_safety.py`)

| Requirement | Result |
|---|---|
| Delta server present | PASS (`delta-exchange-mcp`) |
| `DELTA_MCP_ENV` testnet-only | PASS (`india_testnet`) |
| No production environment selected | PASS (no `prod` token) |
| No credential material / placeholders | PASS (only `DELTA_MCP_ENV`) |
| No trading-capable tool required | PASS |
| Not consumed by production modules | PASS (`core/**`, `config/**` clean) |

All six tests in the file pass. Previously five errored (missing file) and
one passed.

## `.gitignore` durability fix

`.gitignore` ignored `.vscode/`, so a Git checkout would drop the file and
re-break the five tests. Added a narrow negation `!.vscode/mcp.json`,
following the project's existing pattern for required files
(`!.env.example`). The file carries no secrets, so this is safe.

## Safety boundary

The config selects only the India Testnet MCP environment and holds no
key, secret, token, or placeholder. It cannot place production orders.
The archive packaging includes it (the manifest generator does not honour
`.gitignore`), and the file is now also durable under Git.

## Status

MCP configuration contract: **PASS** (was FAIL-preserved-missing-file).
The Phase154 report `PHASE154_MCP_CONFIG_REPAIR.md` is retained as
historical — its "no fabrication" verdict was correct for Phase154.
