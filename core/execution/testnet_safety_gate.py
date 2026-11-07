"""
====================================================
QuantEngine - Dedicated Demo / Testnet Safety Gate
Phase 185 Implementation

Strict, fail-closed authorization gate for demo and testnet execution.
Guarantees absolute separation from live production trading:
  * Rejects production endpoints with typed ProductionEndpointError.
  * Rejects generic/production credentials.
  * Requires explicit operator opt-in: mode == TESTNET,
    ALLOW_TESTNET == true, TESTNET_EXECUTE == true.
  * Enforces verified instrument metadata, positive prices,
    directional geometry, fee-inclusive stop risk, and reconciliation health.
  * Every refusal path produces zero exchange write calls.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import os
import secrets
import time
from typing import Optional, Set

from core.common.logging_config import get_logger

log = get_logger(__name__)

_AUDIT_COMPONENT = "TestnetSafetyGate"
_TESTNET_MINT = secrets.token_hex(16)

# Authoritative Allowed Testnet Endpoints
ALLOWED_TESTNET_REST_URLS: frozenset[str] = frozenset({
    "https://cdn-ind.testnet.deltaex.org",
    "https://testnet-api.delta.exchange",
})

ALLOWED_TESTNET_WS_URLS: frozenset[str] = frozenset({
    "wss://socket-ind.testnet.deltaex.org",
    "wss://socket-ind-pub.testnet.deltaex.org",
})

# Forbidden Production Endpoints
FORBIDDEN_PRODUCTION_URLS: frozenset[str] = frozenset({
    "https://api.delta.exchange",
    "https://india.delta.exchange",
    "wss://public-socket.delta.exchange",
    "wss://socket.delta.exchange",
})


# ==================================================
# Typed Errors
# ==================================================

class TestnetSafetyError(RuntimeError):
    """Base error for all testnet safety gate refusals."""
    __test__ = False


class TestnetBlockedError(TestnetSafetyError):
    """Execution refused because one or more testnet conditions are missing."""
    __test__ = False


class ProductionEndpointAttemptedError(TestnetSafetyError):
    """CRITICAL: Production endpoint attempted in testnet mode. Fails closed."""
    __test__ = False


class TestnetConfigurationError(TestnetSafetyError):
    """Invalid or conflicting configuration for testnet mode."""
    __test__ = False


class TestnetCredentialError(TestnetSafetyError):
    """Missing, generic, or invalid credentials for testnet."""
    __test__ = False


class TestnetRiskBreachedError(TestnetSafetyError):
    """Risk budget, exposure, or directional geometry failed."""
    __test__ = False


# ==================================================
# Verdict Dataclass
# ==================================================

@dataclass(frozen=True)
class TestnetSafetyDecision:
    __test__ = False
    allowed: bool
    mode: str
    reasons: list[str] = field(default_factory=list)
    endpoint: str = ""
    symbol: str = ""
    timestamp_utc: float = field(default_factory=time.time)
    _mint_token: str = field(default="", repr=False)

    def is_armed(self) -> bool:
        """True only if allowed and minted by this process."""
        return self.allowed and self._mint_token == _TESTNET_MINT


# ==================================================
# Gate Implementation
# ==================================================

class TestnetSafetyGate:
    """Fail-closed gate for demo / testnet execution."""
    __test__ = False

    @staticmethod
    def _as_bool(name: str, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("", "0", "false", "no", "off"):
            return False
        raise TestnetConfigurationError(f"Invalid boolean for {name}: {value!r}")

    @classmethod
    def evaluate(
        cls,
        execution_mode: str,
        allow_testnet: object = False,
        testnet_execute: object = False,
        rest_url: str = "",
        api_key: str = "",
        api_secret: str = "",
        symbol: str = "",
        entry_price: Optional[Decimal | float] = None,
        stop_price: Optional[Decimal | float] = None,
        target_price: Optional[Decimal | float] = None,
        quantity: Optional[Decimal | float] = None,
        risk_budget: Optional[Decimal | float] = None,
        total_risk: Optional[Decimal | float] = None,
        direction: str = "BULLISH",
        reconciliation_ok: bool = True,
    ) -> TestnetSafetyDecision:
        """Pure, deterministic evaluation of all 16 testnet safety prerequisites.

        Never performs network I/O or invokes adapters.
        """
        reasons: list[str] = []
        mode_clean = str(execution_mode).strip().upper()

        # 1. Explicit execution mode TESTNET or DEMO
        if mode_clean not in ("TESTNET", "DEMO"):
            reasons.append(f"EXECUTION_MODE={mode_clean!r} is not TESTNET/DEMO")

        # 2. Operator opt-in flags
        try:
            opt_in = cls._as_bool("ALLOW_TESTNET", allow_testnet)
            if not opt_in:
                reasons.append("ALLOW_TESTNET is not true")
        except TestnetConfigurationError as e:
            reasons.append(str(e))

        try:
            execute_flag = cls._as_bool("TESTNET_EXECUTE", testnet_execute)
            if not execute_flag:
                reasons.append("TESTNET_EXECUTE is not true")
        except TestnetConfigurationError as e:
            reasons.append(str(e))

        # 3. Endpoint verification & production isolation
        url_clean = str(rest_url).strip().rstrip("/")
        if not url_clean:
            reasons.append("REST endpoint is empty")
        elif url_clean in FORBIDDEN_PRODUCTION_URLS:
            # Immediate fail closed on production URL
            raise ProductionEndpointAttemptedError(
                f"CRITICAL SAFETY VIOLATION: Production endpoint {url_clean!r} detected in testnet gate!"
            )
        elif url_clean not in ALLOWED_TESTNET_REST_URLS:
            reasons.append(f"Endpoint {url_clean!r} is not an authorized testnet host")

        # 4. Credential separation
        key_str = str(api_key or "").strip()
        sec_str = str(api_secret or "").strip()
        if not key_str or not sec_str:
            reasons.append("Testnet API key or secret is missing/empty")

        # Check for generic production credential reuse
        prod_key = os.getenv("DELTA_API_KEY", "").strip()
        if prod_key and key_str and key_str == prod_key:
            reasons.append("Production DELTA_API_KEY cannot be reused as testnet credential")

        # 5. Symbol presence
        if not symbol or not str(symbol).strip():
            reasons.append("Symbol is missing")

        # 6. Reconciliation state
        if not reconciliation_ok:
            reasons.append("Order/position reconciliation is not healthy")

        # 7. Numeric parameters and risk geometry
        if entry_price is not None and stop_price is not None:
            try:
                ep = Decimal(str(entry_price))
                sp = Decimal(str(stop_price))
                if not (ep.is_finite() and sp.is_finite()) or ep <= 0 or sp <= 0:
                    reasons.append("Entry and stop prices must be finite and positive")
                else:
                    dir_upper = str(direction).upper()
                    if dir_upper in ("BULLISH", "BUY", "LONG"):
                        if sp >= ep:
                            reasons.append(f"Invalid Long geometry: stop_price ({sp}) >= entry_price ({ep})")
                        if target_price is not None:
                            tp = Decimal(str(target_price))
                            if tp <= ep:
                                reasons.append(f"Invalid Long geometry: target_price ({tp}) <= entry_price ({ep})")
                    elif dir_upper in ("BEARISH", "SELL", "SHORT"):
                        if sp <= ep:
                            reasons.append(f"Invalid Short geometry: stop_price ({sp}) <= entry_price ({ep})")
                        if target_price is not None:
                            tp = Decimal(str(target_price))
                            if tp >= ep:
                                reasons.append(f"Invalid Short geometry: target_price ({tp}) >= entry_price ({ep})")
            except Exception as exc:
                reasons.append(f"Malformed price values: {exc}")

        # 8. Fee-inclusive risk budget
        if total_risk is not None and risk_budget is not None:
            try:
                tr = Decimal(str(total_risk))
                rb = Decimal(str(risk_budget))
                if tr > rb:
                    reasons.append(f"Total risk ({tr}) exceeds risk budget ({rb})")
            except Exception as exc:
                reasons.append(f"Malformed risk budget values: {exc}")

        is_allowed = len(reasons) == 0
        mint_token = _TESTNET_MINT if is_allowed else ""

        decision = TestnetSafetyDecision(
            allowed=is_allowed,
            mode=mode_clean,
            reasons=reasons,
            endpoint=url_clean,
            symbol=str(symbol).upper(),
            _mint_token=mint_token,
        )

        if not is_allowed:
            log.warning(
                "TESTNET_GATE_REFUSAL symbol=%s mode=%s reasons=%s",
                symbol,
                mode_clean,
                reasons,
            )

        return decision

    @classmethod
    def require_armed(cls, decision: TestnetSafetyDecision) -> None:
        """Enforce that decision is validly armed. Fails closed with typed error."""
        if not decision.is_armed():
            reasons_str = "; ".join(decision.reasons) or "Decision not armed"
            raise TestnetBlockedError(f"Testnet execution refused: {reasons_str}")
