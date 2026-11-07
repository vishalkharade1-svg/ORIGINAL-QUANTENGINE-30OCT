# Phase154 MCP configuration repair (no fabrication)

## Contract (from `tests/test_delta_mcp_config_safety.py:21`)

`.vscode/mcp.json` must define a delta MCP server selecting ONLY `india_testnet`, carrying no key/secret/token material, no production environment, and no trading-tool requirement. Production code must not consume it (`TestMcpConfigNotConsumedByProduction`).

## Search for authentic source (EXECUTED)

- Worktree: zero `mcp.json` files (`rglob` over full tree, excluding the forensic extract copy).
- Original 3,701-file uploads (`QuantEngine.zip`, `QuantEngine1.zip`) and the 1,697-file Phase131 archive: zero `mcp.json` entries (ZIP namelist inspection, no secret-bearing extraction).
- No `.git` history anywhere; no trusted remote available.

## Decision (per §2.4: do not fabricate)

The exact intended server command/package cannot be established from any authentic source. Inventing `uvx delta-exchange-mcp` (or any command) into the release would be fabrication, and a permissive placeholder would weaken the safety assertions the tests exist to enforce. Therefore:

- NO `.vscode/mcp.json` is created.
- The 5 `TestMcpConfigTestnetSafe` errors are preserved as FAIL/BLOCKED evidence of a missing optional IDE config — not skipped, not xfailed, not faked green.
- `TestMcpConfigNotConsumedByProduction` (6th test in the file) still passes and is unaffected.

## Authoritative information needed to close

The operator-provided MCP server command + args for the read-only evidence workflow, or a ruling that the file is out of scope for the distributable package (in which case the 5 tests should be re-scoped by owner decision, not by agent edit).

Gate status: MCP configuration contract FAIL (missing file), failure preserved honestly.
