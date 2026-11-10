"""
====================================================
QuantEngine - Dedicated Testnet Experiment Authorization Gate
Phase 189 Implementation

Fail-closed authorization preflight gate for gated testnet experiments.
Guarantees absolute separation from live production trading:
  * Rejects production endpoints with typed ProductionEndpointAttemptedError.
  * Rejects templates in PENDING_OPERATOR_APPROVAL state or containing unreplaced placeholders.
  * Enforces verified instrument metadata, single open order, max 20 cumulative orders across restarts.
  * Tracks cumulative order counts against a persistent ledger file.
  * Enforces fail-closed handling for ambiguous order acknowledgments and resting timeouts.
  * Provides a latched kill switch that permanently halts new submissions upon failure.
  * Every refusal path guarantees zero exchange order writes.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import hashlib
import hmac
import base64
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from typing import Any, Dict, List, Optional, Set

from core.common.logging_config import get_logger
from core.execution.testnet_safety_gate import (
    ALLOWED_TESTNET_REST_URLS,
    ALLOWED_TESTNET_WS_URLS,
    FORBIDDEN_PRODUCTION_URLS,
    ProductionEndpointAttemptedError,
    TestnetBlockedError,
    TestnetConfigurationError,
    TestnetSafetyError,
)

log = get_logger(__name__)

_AUDIT_COMPONENT = "TestnetAuthorizationGate"
_GATE_MINT = secrets.token_hex(16)

# Pinned to the Phase 185 Delta product snapshot; do not accept caller-substituted multipliers.
BTCUSD_PRODUCT_ID = 84
BTCUSD_CONTRACT_SIZE_BTC = Decimal("0.001")
BTCUSD_PRODUCT_SNAPSHOT_SHA256 = "e4d838d7d647e4485399ea19aa699058d30ca47cc3806c51bf8e5e2d99950af2"


class AuthorizationState(str, Enum):
    """Explicit lifecycle states for experiment authorization."""
    PENDING_OPERATOR_APPROVAL = "PENDING_OPERATOR_APPROVAL"
    OPERATOR_APPROVED = "OPERATOR_APPROVED"
    EXPIRED = "EXPIRED"
    KILLED = "KILLED"
    REVOKED = "REVOKED"
    INVALID_SCOPE = "INVALID_SCOPE"
    MALFORMED = "MALFORMED"


class OrderLifecycleState(str, Enum):
    """Explicit lifecycle states for individual experiment orders.
    
    Distinguishes the 10 canonical Phase 191 lifecycle states while preserving
    backwards-compatible Phase 189/190 aliases.
    """
    # Phase 191 Canonical 10 States
    NOT_SUBMITTED = "NOT_SUBMITTED"
    RESERVED = "RESERVED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED_CONFIRMED = "CANCELLED_CONFIRMED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    LEDGER_CORRUPTED = "LEDGER_CORRUPTED"

    # Backward-compatible Phase 189/190 aliases
    PENDING_SUBMISSION = "PENDING_SUBMISSION"
    SUBMITTED = "SUBMITTED"
    RESTING = "RESTING"
    CANCELLED_UNFILLED = "CANCELLED_UNFILLED"
    FILLED_POST_CANCEL_REQ = "FILLED_POST_CANCEL_REQ"
    REJECTED_POST_ONLY = "REJECTED_POST_ONLY"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"
    HALTED = "HALTED"


ORDER_STATE_CANONICAL_MAP: Dict[OrderLifecycleState, OrderLifecycleState] = {
    OrderLifecycleState.NOT_SUBMITTED: OrderLifecycleState.NOT_SUBMITTED,
    OrderLifecycleState.RESERVED: OrderLifecycleState.RESERVED,
    OrderLifecycleState.PENDING_SUBMISSION: OrderLifecycleState.RESERVED,
    OrderLifecycleState.SUBMISSION_UNKNOWN: OrderLifecycleState.SUBMISSION_UNKNOWN,
    OrderLifecycleState.SUBMITTED: OrderLifecycleState.SUBMISSION_UNKNOWN,
    OrderLifecycleState.ACKNOWLEDGED: OrderLifecycleState.ACKNOWLEDGED,
    OrderLifecycleState.RESTING: OrderLifecycleState.ACKNOWLEDGED,
    OrderLifecycleState.PARTIALLY_FILLED: OrderLifecycleState.PARTIALLY_FILLED,
    OrderLifecycleState.FILLED: OrderLifecycleState.FILLED,
    OrderLifecycleState.FILLED_POST_CANCEL_REQ: OrderLifecycleState.FILLED,
    OrderLifecycleState.CANCEL_REQUESTED: OrderLifecycleState.CANCEL_REQUESTED,
    OrderLifecycleState.CANCELLED_CONFIRMED: OrderLifecycleState.CANCELLED_CONFIRMED,
    OrderLifecycleState.CANCELLED_UNFILLED: OrderLifecycleState.CANCELLED_CONFIRMED,
    OrderLifecycleState.REJECTED_POST_ONLY: OrderLifecycleState.CANCELLED_CONFIRMED,
    OrderLifecycleState.RECONCILIATION_REQUIRED: OrderLifecycleState.RECONCILIATION_REQUIRED,
    OrderLifecycleState.AMBIGUOUS_STATE: OrderLifecycleState.RECONCILIATION_REQUIRED,
    OrderLifecycleState.HALTED: OrderLifecycleState.RECONCILIATION_REQUIRED,
    OrderLifecycleState.LEDGER_CORRUPTED: OrderLifecycleState.LEDGER_CORRUPTED,
}


class AuthorizationIntegrityError(TestnetSafetyError):
    """Authorization record is missing, malformed, expired, or unapproved."""
    __test__ = False


class KillSwitchActiveError(TestnetSafetyError):
    """CRITICAL: Kill switch has been triggered; execution is permanently halted."""
    __test__ = False


class OrderLimitExceededError(TestnetSafetyError):
    """Cumulative or concurrent order limits exceeded."""
    __test__ = False


class AmbiguousOrderStateError(TestnetSafetyError):
    """Matching engine acknowledgment timed out or order status is unknown."""
    __test__ = False


class LockTimeoutError(TestnetSafetyError):
    """Cross-process lock acquisition timed out within bounded window."""
    __test__ = False


class LedgerCorruptedError(TestnetSafetyError):
    """Persistent ledger file contains unparseable, truncated, or conflicting records."""
    __test__ = False


class DuplicateClientOrderIdError(TestnetSafetyError):
    """Client order ID was already submitted or reserved in ledger."""
    __test__ = False


class CrossProcessFileLock:
    """Bounded, crash-safe cross-process file lock supporting Windows (msvcrt) and POSIX (fcntl).
    
    Provides reentrancy per-thread within the same process, and strict mutual
    exclusion across distinct processes. If the holding process crashes, the OS
    automatically frees kernel-held file locks, preventing permanent deadlocks.
    """
    _local = threading.local()

    def __init__(self, lock_path: Path | str, timeout_seconds: float = 5.0, poll_interval: float = 0.02):
        self.lock_path = Path(lock_path)
        self.timeout_seconds = float(timeout_seconds)
        self.poll_interval = float(poll_interval)
        self._fd: Optional[int] = None
        self._file_obj = None

    def _normalize_key(self) -> str:
        k = str(self.lock_path.resolve())
        return k.lower() if sys.platform == "win32" else k

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not hasattr(CrossProcessFileLock._local, "held_locks"):
            CrossProcessFileLock._local.held_locks = {}

        path_key = self._normalize_key()
        if path_key in CrossProcessFileLock._local.held_locks:
            CrossProcessFileLock._local.held_locks[path_key] += 1
            return

        start_time = time.monotonic()
        f = open(self.lock_path, "a+b")
        fd = f.fileno()

        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file_obj = f
                self._fd = fd
                CrossProcessFileLock._local.held_locks[path_key] = 1
                return
            except (OSError, IOError) as exc:
                elapsed = time.monotonic() - start_time
                if elapsed >= self.timeout_seconds:
                    try:
                        f.close()
                    except Exception:
                        pass
                    raise LockTimeoutError(
                        f"Failed to acquire cross-process lock {self.lock_path} within {self.timeout_seconds:.1f}s: {exc}"
                    ) from exc
                time.sleep(self.poll_interval)

    def release(self) -> None:
        path_key = self._normalize_key()
        if not hasattr(CrossProcessFileLock._local, "held_locks") or path_key not in CrossProcessFileLock._local.held_locks:
            return

        CrossProcessFileLock._local.held_locks[path_key] -= 1
        if CrossProcessFileLock._local.held_locks[path_key] > 0:
            return  # still held by outer reentrant context

        del CrossProcessFileLock._local.held_locks[path_key]
        if self._file_obj and not self._file_obj.closed:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._file_obj.seek(0)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception as exc:
                log.warning("Exception during lock release for %s: %s", self.lock_path, exc)
            finally:
                try:
                    self._file_obj.close()
                except Exception:
                    pass
                self._file_obj = None
                self._fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


@dataclass(frozen=True)
class ExperimentScope:
    """Rigid boundaries authorized for a specific experiment."""
    venue: str
    target_rest_url: str
    target_ws_url: str
    allowed_symbols: Set[str]
    allowed_product_ids: Set[int]
    max_cumulative_orders: int
    max_simultaneous_open_orders: int
    max_order_size_contracts: Decimal
    max_order_notional_usd: Decimal
    max_loss_budget_usd: Decimal
    max_order_wait_seconds: float
    require_post_only: bool
    forbid_market_conversion: bool
    require_valid_book: bool = False
    # BTCUSD inverse contract value from the observed Delta product record.
    # The signed authorization binds this multiplier; callers cannot choose
    # a smaller multiplier to evade the USD notional ceiling.
    contract_size_btc: Optional[Decimal] = None
    contract_metadata_product_id: Optional[int] = None
    contract_metadata_sha256: str = ""


@dataclass
class OperatorAuthorizationRecord:
    """Parsed, verifiable authorization document."""
    authorization_id: str
    state: AuthorizationState
    operator_identity: str
    signed_timestamp_utc: str
    expiry_timestamp_utc: str
    scope: ExperimentScope
    document_sha256: str
    signature_payload: str
    raw_content: str = ""

    @staticmethod
    def _parse_utc_timestamp(value: str) -> Optional[float]:
        """Parse an ISO-8601 timestamp; naive timestamps are rejected."""
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            return parsed.astimezone(timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    def signature_message(self) -> bytes:
        """Canonical, scope-bound message authenticated by the operator signature."""
        scope = self.scope
        payload = {
            "authorization_id": self.authorization_id,
            "operator_identity": self.operator_identity,
            "signed_timestamp_utc": self.signed_timestamp_utc,
            "expiry_timestamp_utc": self.expiry_timestamp_utc,
            "document_sha256": self.document_sha256,
            "scope": {
                "venue": scope.venue,
                "target_rest_url": scope.target_rest_url,
                "target_ws_url": scope.target_ws_url,
                "allowed_symbols": sorted(scope.allowed_symbols),
                "allowed_product_ids": sorted(scope.allowed_product_ids),
                "max_cumulative_orders": scope.max_cumulative_orders,
                "max_simultaneous_open_orders": scope.max_simultaneous_open_orders,
                "max_order_size_contracts": str(scope.max_order_size_contracts),
                "max_order_notional_usd": str(scope.max_order_notional_usd),
                "contract_size_btc": (str(scope.contract_size_btc) if scope.contract_size_btc is not None else None),
                "contract_metadata_product_id": scope.contract_metadata_product_id,
                "contract_metadata_sha256": scope.contract_metadata_sha256,
                "max_loss_budget_usd": str(scope.max_loss_budget_usd),
                "max_order_wait_seconds": scope.max_order_wait_seconds,
                "require_post_only": scope.require_post_only,
                "forbid_market_conversion": scope.forbid_market_conversion,
                "require_valid_book": scope.require_valid_book,
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    def is_currently_valid(self, now_utc_seconds: Optional[float] = None) -> bool:
        """Verify approval, time bounds, and Ed25519 signature; fail closed by default.

        The verification key must be supplied as base64-encoded raw Ed25519 public
        key in QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY. Signature format is
        `ed25519:<base64 signature>`. The signed message includes the full scope.
        """
        if self.state != AuthorizationState.OPERATOR_APPROVED:
            return False
        if not self.authorization_id or self.authorization_id.startswith("["):
            return False
        if not self.operator_identity or self.operator_identity.startswith("["):
            return False
        public_key_b64 = os.environ.get("QUANTENGINE_TESTNET_AUTH_PUBLIC_KEY", "")
        if not public_key_b64:
            return False
        try:
            public_key_bytes = base64.b64decode(public_key_b64, validate=True)
            if len(public_key_bytes) != 32:
                return False
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        except (ValueError, TypeError):
            return False
        signed_at = self._parse_utc_timestamp(self.signed_timestamp_utc)
        expires_at = self._parse_utc_timestamp(self.expiry_timestamp_utc)
        now = time.time() if now_utc_seconds is None else float(now_utc_seconds)
        if signed_at is None or expires_at is None or not (signed_at < expires_at):
            return False
        # Allow at most 60 seconds of clock skew; reject future-dated approvals.
        if signed_at > now + 60.0 or expires_at <= now:
            return False
        if not isinstance(self.signature_payload, str) or not self.signature_payload.startswith("ed25519:"):
            return False
        try:
            signature = base64.b64decode(self.signature_payload.split(":", 1)[1], validate=True)
            if len(signature) != 64:
                return False
            public_key.verify(signature, self.signature_message())
            return True
        except (ValueError, TypeError, InvalidSignature):
            return False


def sign_authorization_record(record: OperatorAuthorizationRecord, private_key: Ed25519PrivateKey | bytes) -> str:
    """Create an Ed25519 signature for trusted authorization tooling and tests.

    Production deployments should keep the private key with the operator approval
    workflow and configure only the raw public key (base64) in QuantEngine.
    """
    if isinstance(private_key, bytes):
        if len(private_key) != 32:
            raise ValueError("Ed25519 private key must be exactly 32 raw bytes")
        private_key = Ed25519PrivateKey.from_private_bytes(private_key)
    signature = private_key.sign(record.signature_message())
    return "ed25519:" + base64.b64encode(signature).decode("ascii")


@dataclass(frozen=True)
class AuthorizationDecision:
    """Verdict rendered by the authorization gate."""
    __test__ = False
    authorized: bool
    state: AuthorizationState
    reasons: List[str] = field(default_factory=list)
    cumulative_orders_placed: int = 0
    current_open_orders: int = 0
    current_realized_loss_usd: Decimal = Decimal("0.0")
    timestamp_utc: float = field(default_factory=time.time)
    authorized_symbol: str = ""
    authorized_rest_url: str = ""
    authorized_product_id: Optional[int] = None
    authorized_order_size_contracts: Optional[Decimal] = None
    authorized_post_only: Optional[bool] = None
    authorized_order_details: tuple = ()
    authorized_client_order_id: str = ""
    _mint_token: str = field(default="", repr=False)
    _seal: str = field(default="", repr=False)

    def _seal_payload(self) -> bytes:
        payload = {
            "authorized": self.authorized,
            "state": self.state.value if isinstance(self.state, Enum) else str(self.state),
            "reasons": [str(reason) for reason in self.reasons],
            "cumulative_orders_placed": self.cumulative_orders_placed,
            "current_open_orders": self.current_open_orders,
            "current_realized_loss_usd": str(self.current_realized_loss_usd),
            "timestamp_utc": self.timestamp_utc,
            "authorized_symbol": self.authorized_symbol,
            "authorized_rest_url": self.authorized_rest_url,
            "authorized_product_id": self.authorized_product_id,
            "authorized_order_size_contracts": (
                str(self.authorized_order_size_contracts)
                if self.authorized_order_size_contracts is not None else None
            ),
            "authorized_post_only": self.authorized_post_only,
            "authorized_order_details": [
                [str(key), str(value)] for key, value in self.authorized_order_details
            ],
            "authorized_client_order_id": self.authorized_client_order_id,
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

    def _expected_seal(self) -> str:
        return hmac.new(
            _GATE_MINT.encode("ascii"), self._seal_payload(), hashlib.sha256
        ).hexdigest()

    def is_armed(self) -> bool:
        if not self.authorized or self._mint_token != _GATE_MINT or not self._seal:
            return False
        return hmac.compare_digest(self._seal, self._expected_seal())


def _mint_reserved_decision(**kwargs) -> AuthorizationDecision:
    """Create the sole write-capable decision: an atomic ledger reservation."""
    decision = AuthorizationDecision(**kwargs)
    if decision.authorized and decision._mint_token == _GATE_MINT:
        object.__setattr__(decision, "_seal", decision._expected_seal())
    return decision


class TestnetAuthorizationGate:
    """Fail-closed gate validating authorization, scope, persistent order count, and state."""
    __test__ = False

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        default_scope: Optional[ExperimentScope] = None,
    ):
        self.ledger_path = Path(ledger_path or (
            Path(__file__).resolve().parents[2] / "research" / "results" / "phase189_testnet_experiment_ledger.jsonl"
        ))
        self.lock_path = self.ledger_path.with_suffix(".lock")
        self.scope = default_scope or ExperimentScope(
            venue="DELTA_INDIA_TESTNET",
            target_rest_url="https://cdn-ind.testnet.deltaex.org",
            target_ws_url="wss://socket-ind.testnet.deltaex.org",
            allowed_symbols={"BTCUSD"},
            allowed_product_ids={84},
            max_cumulative_orders=20,
            max_simultaneous_open_orders=1,
            max_order_size_contracts=Decimal("1.0"),
            max_order_notional_usd=Decimal("100.00"),
            max_loss_budget_usd=Decimal("5.00"),
            max_order_wait_seconds=120.0,
            require_post_only=True,
            forbid_market_conversion=True,
            contract_size_btc=BTCUSD_CONTRACT_SIZE_BTC,
            contract_metadata_product_id=BTCUSD_PRODUCT_ID,
            contract_metadata_sha256=BTCUSD_PRODUCT_SNAPSHOT_SHA256,
        )
        self._kill_switch_active: bool = False
        self._kill_switch_reason: str = ""
        self._active_open_orders: Dict[str, Dict[str, Any]] = {}
        self._ambiguous_orders: Dict[str, Dict[str, Any]] = {}
        self._ledger_corrupted: bool = False
        self._ledger_corruption_reason: str = ""

    def activate_kill_switch(self, reason: str) -> None:
        """Permanently latch kill switch. Refuses all subsequent order actions."""
        self._kill_switch_active = True
        self._kill_switch_reason = str(reason)
        log.critical("TESTNET_KILL_SWITCH_ACTIVATED reason=%s", reason)

    @property
    def is_killed(self) -> bool:
        return self._kill_switch_active

    def parse_authorization_document(self, content_or_path: str | Path) -> OperatorAuthorizationRecord:
        """Parse authorization document and strictly detect template placeholders."""
        if isinstance(content_or_path, Path) or (isinstance(content_or_path, str) and os.path.exists(content_or_path)):
            path = Path(content_or_path)
            raw = path.read_text(encoding="utf-8")
        else:
            raw = str(content_or_path)

        # Hash a canonical document with the signature field blanked to avoid a
        # circular dependency between the signature and the document digest.
        canonical_for_hash = re.sub(
            r"(?im)^(\s*-?\s*(?:\*\*)?Operator Signature(?:\*\*)?\s*:\s*).*$",
            r"\1",
            raw.replace("\r\n", "\n").replace("\r", "\n"),
        ).rstrip() + "\n"
        doc_hash = hashlib.sha256(canonical_for_hash.encode("utf-8")).hexdigest()

        # Check for unreplaced template placeholders
        has_placeholders = bool(re.search(r"\[(OPERATOR_[A-Z0-9_]+|REQUIRED|PENDING|TODO)\]", raw, re.IGNORECASE))
        has_pending_status = "PENDING_OPERATOR_APPROVAL" in raw

        # Parse fields
        auth_id = ""
        operator = ""
        signed_ts = ""
        expiry_ts = ""
        sig_payload = ""

        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("- **Authorization ID**:") or line.startswith("Authorization ID:"):
                auth_id = line.split(":", 1)[1].strip(" *`")
            elif line.startswith("- **Authorizing Operator**:") or line.startswith("Authorizing Operator:"):
                operator = line.split(":", 1)[1].strip(" *`")
            elif line.startswith("- **Signed Timestamp UTC**:") or line.startswith("Signed Timestamp UTC:"):
                signed_ts = line.split(":", 1)[1].strip(" *`")
            elif line.startswith("- **Expiry Timestamp UTC**:") or line.startswith("Expiry Timestamp UTC:"):
                expiry_ts = line.split(":", 1)[1].strip(" *`")
            elif line.startswith("- **Operator Signature**:") or line.startswith("Operator Signature:"):
                sig_payload = line.split(":", 1)[1].strip(" *`")

        if has_placeholders or has_pending_status:
            state = AuthorizationState.PENDING_OPERATOR_APPROVAL
        elif not operator or not sig_payload or sig_payload.startswith("["):
            state = AuthorizationState.MALFORMED
        else:
            state = AuthorizationState.OPERATOR_APPROVED

        return OperatorAuthorizationRecord(
            authorization_id=auth_id or "P189-UNIDENTIFIED",
            state=state,
            operator_identity=operator,
            signed_timestamp_utc=signed_ts,
            expiry_timestamp_utc=expiry_ts,
            scope=self.scope,
            document_sha256=doc_hash,
            signature_payload=sig_payload,
            raw_content=raw,
        )

    def read_cumulative_orders_from_ledger(self) -> int:
        """Inspect persistent append-only ledger to prevent reset across restarts.

        Detects file corruption, unparseable lines, duplicate order IDs, and conflicting states.
        Fails closed by latching _ledger_corrupted = True on any integrity fault.
        """
        if not self.ledger_path.exists():
            return 0

        reserved_order_ids: Set[str] = set()
        submitted_order_ids: Set[str] = set()
        all_order_ids: Set[str] = set()
        unidentified_orders_count = 0

        with CrossProcessFileLock(self.lock_path):
            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    for line_no, raw_line in enumerate(f, start=1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            if not isinstance(record, dict) or "event" not in record:
                                self._ledger_corrupted = True
                                self._ledger_corruption_reason = f"Malformed record structure at line {line_no}"
                                continue

                            event = record.get("event")
                            data = record.get("data", {}) if isinstance(record.get("data"), dict) else {}
                            cl_ord_id = data.get("cl_ord_id")

                            if event == "ORDER_RESERVED":
                                if cl_ord_id:
                                    if cl_ord_id in reserved_order_ids:
                                        self._ledger_corrupted = True
                                        self._ledger_corruption_reason = f"Duplicate cl_ord_id reservation {cl_ord_id!r} at line {line_no}"
                                    reserved_order_ids.add(cl_ord_id)
                                    all_order_ids.add(cl_ord_id)
                                else:
                                    unidentified_orders_count += 1

                            elif event in ("ORDER_SUBMITTED", "ORDER_PLACED"):
                                if cl_ord_id:
                                    if cl_ord_id in submitted_order_ids:
                                        self._ledger_corrupted = True
                                        self._ledger_corruption_reason = f"Duplicate cl_ord_id {cl_ord_id!r} at line {line_no}"
                                    submitted_order_ids.add(cl_ord_id)
                                    all_order_ids.add(cl_ord_id)
                                else:
                                    unidentified_orders_count += 1
                        except Exception as parse_err:
                            self._ledger_corrupted = True
                            self._ledger_corruption_reason = f"Corrupted JSON at line {line_no}: {parse_err}"
            except Exception as exc:
                self._ledger_corrupted = True
                self._ledger_corruption_reason = f"IO error reading ledger: {exc}"
                log.error("Failed to read experiment ledger %s: %s", self.ledger_path, exc)

        return len(all_order_ids) + unidentified_orders_count

    def record_order_event_to_ledger(self, event_type: str, data: Dict[str, Any]) -> None:
        """Durable append-only audit record of order transitions with fsync."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp_utc": time.time(),
            "event": event_type,
            "data": data,
        }
        with CrossProcessFileLock(self.lock_path):
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def evaluate_preflight(
        self,
        auth_record: OperatorAuthorizationRecord,
        rest_url: str,
        symbol: str,
        product_id: int,
        order_size_contracts: Decimal | float,
        post_only: bool = True,
        cumulative_realized_loss: Decimal | float = Decimal("0.0"),
        book_tracker: Optional[Any] = None,
        limit_price: Decimal | float | str | None = None,
    ) -> AuthorizationDecision:
        """Evaluate preflight gate prior to order placement attempt.

        Guarantees:
          - Zero network I/O.
          - Fail closed on production URLs.
          - Fail closed on unapproved / placeholder authorizations.
          - Fail closed on order limit (cumulative >= 20 or open >= 1).
          - Fail closed on loss budget breach.
          - Fail closed on corrupted ledger or unreconciled ambiguous orders.
          - Fail closed on invalid, crossed, or stale order book state.
        """
        reasons: List[str] = []

        # 1. Kill switch check
        if self._kill_switch_active:
            reasons.append(f"Kill switch active: {self._kill_switch_reason}")
            return AuthorizationDecision(
                authorized=False,
                state=AuthorizationState.KILLED,
                reasons=reasons,
            )

        # 2. Endpoint validation & production isolation
        url_clean = str(rest_url or "").strip().rstrip("/")
        if not url_clean:
            reasons.append("REST endpoint is empty")
        elif url_clean in FORBIDDEN_PRODUCTION_URLS:
            # Immediate fail closed on production URL
            raise ProductionEndpointAttemptedError(
                f"CRITICAL SAFETY VIOLATION: Production endpoint {url_clean!r} attempted!"
            )
        elif url_clean not in ALLOWED_TESTNET_REST_URLS:
            reasons.append(f"Endpoint {url_clean!r} is not an authorized testnet host")

        # 3. Authorization status
        if auth_record.state == AuthorizationState.PENDING_OPERATOR_APPROVAL:
            reasons.append(
                "Authorization record is in PENDING_OPERATOR_APPROVAL state (requires signed operator signoff)"
            )
        elif auth_record.state != AuthorizationState.OPERATOR_APPROVED:
            reasons.append(f"Authorization record state {auth_record.state.value} is not approved")
        elif not auth_record.is_currently_valid():
            reasons.append("Authorization record signature or operator credentials invalid")

        # 4. Scope and instrument check. The signed operator scope must
        # agree with the gate's pinned notional boundary; otherwise fail closed.
        signed_scope = auth_record.scope
        if (
            signed_scope.max_order_notional_usd != self.scope.max_order_notional_usd
            or signed_scope.contract_size_btc != self.scope.contract_size_btc
            or signed_scope.contract_metadata_product_id != self.scope.contract_metadata_product_id
            or signed_scope.contract_metadata_sha256 != self.scope.contract_metadata_sha256
        ):
            reasons.append("Signed authorization notional scope does not match the gate's pinned notional boundary")

        sym_clean = str(symbol or "").strip().upper()
        if sym_clean not in self.scope.allowed_symbols:
            reasons.append(f"Symbol {sym_clean!r} not in authorized scope: {self.scope.allowed_symbols}")

        if product_id not in self.scope.allowed_product_ids:
            reasons.append(f"Product ID {product_id} not in authorized scope: {self.scope.allowed_product_ids}")

        # 5. Order sizing and verified product metadata.
        sz = None
        try:
            sz = Decimal(str(order_size_contracts))
            if not sz.is_finite():
                reasons.append("Order size must be finite")
            elif sz <= 0:
                reasons.append("Order size must be positive")
            elif sz > self.scope.max_order_size_contracts:
                reasons.append(
                    f"Order size ({sz}) exceeds maximum authorized ({self.scope.max_order_size_contracts})"
                )
        except Exception:
            reasons.append("Malformed order size")

        contract_size = self.scope.contract_size_btc
        metadata_valid = True
        if sym_clean != "BTCUSD" or product_id != BTCUSD_PRODUCT_ID:
            reasons.append("Notional metadata is authorized only for BTCUSD Product ID 84")
            metadata_valid = False
        if self.scope.contract_metadata_product_id != product_id:
            reasons.append("Contract metadata product ID is missing or does not match requested product")
            metadata_valid = False
        if self.scope.contract_metadata_sha256 != BTCUSD_PRODUCT_SNAPSHOT_SHA256:
            reasons.append("Contract metadata snapshot SHA-256 does not match the pinned verified BTCUSD product snapshot")
            metadata_valid = False
        try:
            if contract_size is None:
                raise ValueError("missing multiplier")
            contract_size = Decimal(str(contract_size))
            if not contract_size.is_finite() or contract_size <= 0:
                raise ValueError("invalid multiplier")
            if contract_size != BTCUSD_CONTRACT_SIZE_BTC:
                raise ValueError("multiplier differs from pinned BTCUSD product metadata")
        except Exception:
            reasons.append("Verified BTCUSD contract multiplier is missing or invalid")
            metadata_valid = False

        # 5A. The gate itself requires a priced order and enforces its USD ceiling.
        if limit_price is None:
            reasons.append("Limit price is required to authorize USD notional")
        elif sz is not None and sz.is_finite() and metadata_valid:
            try:
                price = Decimal(str(limit_price))
                if not price.is_finite() or price <= 0:
                    reasons.append("Limit price must be finite and positive")
                else:
                    notional = sz * contract_size * price
                    if notional > self.scope.max_order_notional_usd:
                        reasons.append(
                            f"Order notional (${notional}) exceeds maximum authorized "
                            f"(${self.scope.max_order_notional_usd})"
                        )
            except Exception:
                reasons.append("Malformed limit price or contract-size metadata")
        elif limit_price is not None:
            try:
                price = Decimal(str(limit_price))
                if not price.is_finite() or price <= 0:
                    reasons.append("Limit price must be finite and positive")
            except Exception:
                reasons.append("Malformed limit price")

        # 6. Post-only enforcement
        if self.scope.require_post_only and not post_only:
            reasons.append("Post-only is mandatory in experiment scope; taker orders strictly prohibited")

        # 7. Ambiguous state check
        if len(self._ambiguous_orders) > 0:
            reasons.append(
                f"Matching engine has {len(self._ambiguous_orders)} ambiguous/unreconciled orders; placement halted"
            )

        # 8. Single-open-order constraint
        current_open = len(self._active_open_orders)
        if current_open >= self.scope.max_simultaneous_open_orders:
            reasons.append(
                f"Single-open-order limit reached ({current_open} open >= {self.scope.max_simultaneous_open_orders})"
            )

        # 9. Persistent cumulative order count across restarts
        cumulative_orders = self.read_cumulative_orders_from_ledger()
        if self._ledger_corrupted:
            reasons.append(
                f"Persistent ledger corrupted or unparseable: {self._ledger_corruption_reason}; failing closed"
            )
        elif cumulative_orders >= self.scope.max_cumulative_orders:
            reasons.append(
                f"Cumulative experiment order limit reached ({cumulative_orders} placed >= {self.scope.max_cumulative_orders})"
            )

        # 10. Realized loss budget check
        try:
            loss = Decimal(str(cumulative_realized_loss))
            if loss < Decimal("0.0"):
                loss = abs(loss)
            if loss >= self.scope.max_loss_budget_usd:
                reasons.append(
                    f"Cumulative loss (${loss}) has exhausted authorized budget (${self.scope.max_loss_budget_usd})"
                )
        except Exception as exc:
            reasons.append(f"Malformed loss value: {exc}")

        # 11. Market Data Order Book Validity
        if book_tracker is not None:
            if hasattr(book_tracker, "is_execution_eligible"):
                eligible, book_reasons = book_tracker.is_execution_eligible()
                if not eligible:
                    reasons.append(
                        f"Market data order book is not execution-eligible: {'; '.join(book_reasons)}"
                    )
            elif hasattr(book_tracker, "state"):
                if str(getattr(book_tracker, "state", "")).upper() != "VALID":
                    reasons.append(f"Market data order book state {book_tracker.state} is not VALID")
        elif getattr(self.scope, "require_valid_book", False):
            reasons.append("Market data order book validation required by scope, but no book tracker provided")

        is_authorized = len(reasons) == 0
        # Preflight is diagnostic only. It never grants write authority; only
        # check_and_reserve_order() may mint a transport capability.
        mint_token = ""

        return AuthorizationDecision(
            authorized=is_authorized,
            state=auth_record.state if is_authorized else (
                AuthorizationState.KILLED if self._kill_switch_active else
                AuthorizationState.INVALID_SCOPE if not is_authorized and auth_record.state == AuthorizationState.OPERATOR_APPROVED else
                auth_record.state
            ),
            reasons=reasons,
            cumulative_orders_placed=cumulative_orders,
            current_open_orders=current_open,
            current_realized_loss_usd=Decimal(str(cumulative_realized_loss)),
            authorized_symbol=sym_clean if is_authorized else "",
            authorized_rest_url=url_clean if is_authorized else "",
            authorized_product_id=product_id if is_authorized else None,
            authorized_order_size_contracts=sz if is_authorized else None,
            authorized_post_only=bool(post_only) if is_authorized else None,
            _mint_token=mint_token,
        )

    def check_and_reserve_order(
        self,
        auth_record: OperatorAuthorizationRecord,
        rest_url: str,
        symbol: str,
        product_id: int,
        order_size_contracts: Decimal | float,
        cl_ord_id: str,
        order_details: Optional[Dict[str, Any]] = None,
        post_only: bool = True,
        cumulative_realized_loss: Decimal | float = Decimal("0.0"),
        lock_timeout_seconds: float = 5.0,
        book_tracker: Optional[Any] = None,
    ) -> AuthorizationDecision:
        """Atomic check-and-reserve transaction under cross-process file lock.

        Guarantees:
          - Serialized check-and-reserve prevents concurrent processes consuming > 20 orders.
          - Rejects duplicate cl_ord_id immediately.
          - Flushes and fsyncs ORDER_RESERVED record before releasing lock.
          - Fails closed on any corruption, limit breach, or lock timeout.
          - Fails closed on invalid, crossed, or stale order book state.
        """
        cl_ord_id_clean = str(cl_ord_id or "").strip()
        if not cl_ord_id_clean:
            return AuthorizationDecision(
                authorized=False,
                state=AuthorizationState.MALFORMED,
                reasons=["Empty or invalid cl_ord_id"],
            )

        with CrossProcessFileLock(self.lock_path, timeout_seconds=lock_timeout_seconds):
            # 1. Run full preflight evaluation
            decision = self.evaluate_preflight(
                auth_record=auth_record,
                rest_url=rest_url,
                symbol=symbol,
                product_id=product_id,
                order_size_contracts=order_size_contracts,
                post_only=post_only,
                cumulative_realized_loss=cumulative_realized_loss,
                book_tracker=book_tracker,
                limit_price=(
                    order_details.get("limit_price")
                    if isinstance(order_details, dict) else None
                ),
            )
            if not decision.authorized:
                return decision

            # Preflight alone is diagnostic. A write-capable reservation must
            # bind every field used by the transport capability before any
            # durable reservation is appended.
            required_details = {"side", "limit_price", "post_only"}
            if (not isinstance(order_details, dict)
                    or set(order_details) != required_details):
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.MALFORMED,
                    reasons=[
                        "Order reservation requires exactly side, limit_price, and post_only details"
                    ],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                    current_realized_loss_usd=decision.current_realized_loss_usd,
                )
            side = str(order_details.get("side", "")).strip().lower()
            if side not in {"buy", "sell"}:
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.MALFORMED,
                    reasons=["Order side must be buy or sell"],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                    current_realized_loss_usd=decision.current_realized_loss_usd,
                )
            if (type(order_details.get("post_only")) is not bool
                    or order_details["post_only"] is not post_only):
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.MALFORMED,
                    reasons=["Reserved post_only detail must exactly match the authorization request"],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                    current_realized_loss_usd=decision.current_realized_loss_usd,
                )
            try:
                limit_price = Decimal(str(order_details["limit_price"]))
                contract_size = Decimal(str(self.scope.contract_size_btc))
                if (product_id != BTCUSD_PRODUCT_ID
                        or self.scope.contract_metadata_product_id != BTCUSD_PRODUCT_ID
                        or self.scope.contract_metadata_sha256 != BTCUSD_PRODUCT_SNAPSHOT_SHA256
                        or not limit_price.is_finite() or limit_price <= 0
                        or not contract_size.is_finite() or contract_size != BTCUSD_CONTRACT_SIZE_BTC):
                    raise ValueError("unverified product metadata or invalid price/multiplier")
                notional_usd = (
                    decision.authorized_order_size_contracts
                    * contract_size * limit_price
                )
            except Exception:
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.MALFORMED,
                    reasons=["Limit price or authorized contract size is invalid"],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                    current_realized_loss_usd=decision.current_realized_loss_usd,
                )
            if notional_usd > self.scope.max_order_notional_usd:
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.INVALID_SCOPE,
                    reasons=[
                        f"Order notional (${notional_usd}) exceeds maximum authorized "
                        f"(${self.scope.max_order_notional_usd})"
                    ],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                    current_realized_loss_usd=decision.current_realized_loss_usd,
                )

            # 2. Check for duplicate cl_ord_id in active or ambiguous tracking
            if cl_ord_id_clean in self._active_open_orders or cl_ord_id_clean in self._ambiguous_orders:
                return AuthorizationDecision(
                    authorized=False,
                    state=AuthorizationState.INVALID_SCOPE,
                    reasons=[f"Duplicate cl_ord_id {cl_ord_id_clean!r} already active or ambiguous"],
                    cumulative_orders_placed=decision.cumulative_orders_placed,
                    current_open_orders=len(self._active_open_orders),
                )

            # 3. Check for duplicate cl_ord_id in persistent ledger
            if self.ledger_path.exists():
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    for line_no, raw_line in enumerate(f, start=1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            d = rec.get("data", {}) if isinstance(rec.get("data"), dict) else {}
                            if d.get("cl_ord_id") == cl_ord_id_clean:
                                return AuthorizationDecision(
                                    authorized=False,
                                    state=AuthorizationState.INVALID_SCOPE,
                                    reasons=[f"Duplicate cl_ord_id {cl_ord_id_clean!r} already recorded in ledger at line {line_no}"],
                                    cumulative_orders_placed=decision.cumulative_orders_placed,
                                    current_open_orders=len(self._active_open_orders),
                                )
                        except Exception:
                            pass

            # 4. Atomic reservation append with fsync
            reservation_data = {
                "cl_ord_id": cl_ord_id_clean,
                "symbol": symbol,
                "product_id": product_id,
                "order_size": str(order_size_contracts),
                "state": OrderLifecycleState.RESERVED.value,
                "timestamp_monotonic": time.monotonic(),
            }
            # Never let caller-supplied details overwrite reservation
            # identity, product scope, quantity, state, or timestamps.
            reservation_data.update({
                "side": side,
                "limit_price": format(limit_price, "f"),
                "post_only": post_only,
                "notional_usd": str(notional_usd),
                "contract_size_btc": format(contract_size, "f"),
                "contract_metadata_product_id": self.scope.contract_metadata_product_id,
                "contract_metadata_sha256": self.scope.contract_metadata_sha256,
                "notional_formula": "contracts * BTC_per_contract * limit_price_USD",
            })

            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                entry = {
                    "timestamp_utc": time.time(),
                    "event": "ORDER_RESERVED",
                    "data": reservation_data,
                }
                f.write(json.dumps(entry, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())

            # 5. Update local tracking state
            self._active_open_orders[cl_ord_id_clean] = {
                "state": OrderLifecycleState.RESERVED,
                "reservation_time": time.monotonic(),
                "details": reservation_data,
            }

            return _mint_reserved_decision(
                authorized=True,
                state=auth_record.state,
                reasons=[],
                cumulative_orders_placed=decision.cumulative_orders_placed + 1,
                current_open_orders=len(self._active_open_orders),
                current_realized_loss_usd=decision.current_realized_loss_usd,
                authorized_symbol=decision.authorized_symbol,
                authorized_rest_url=decision.authorized_rest_url,
                authorized_product_id=decision.authorized_product_id,
                authorized_order_size_contracts=decision.authorized_order_size_contracts,
                authorized_post_only=decision.authorized_post_only,
                authorized_order_details=tuple(sorted(
                    (str(key), str(value)) for key, value in {
                        "side": side,
                        "limit_price": format(limit_price, "f"),
                        "post_only": post_only,
                        "notional_usd": str(notional_usd),
                        "contract_size_btc": format(contract_size, "f"),
                        "contract_metadata_product_id": self.scope.contract_metadata_product_id,
                        "contract_metadata_sha256": self.scope.contract_metadata_sha256,
                    }.items()
                )),
                authorized_client_order_id=cl_ord_id_clean,
                _mint_token=_GATE_MINT,
            )

    def recover_and_reconcile_state(self) -> Dict[str, Any]:
        """Deterministic restart recovery scanning the persistent ledger.

        Reconstructs order states and enforces fail-closed posture:
          - Orders left in RESERVED or SUBMITTED state without terminal record enter RECONCILIATION_REQUIRED.
          - Corrupted records latch _ledger_corrupted = True and OrderLifecycleState.LEDGER_CORRUPTED.
          - Resting orders enter ACKNOWLEDGED.
          - Releases zero risk reservations until explicit reconciliation occurs.
        """
        summary: Dict[str, Any] = {
            "recovered_orders": 0,
            "active_open": [],
            "ambiguous": [],
            "terminal": [],
            "ledger_corrupted": False,
            "corruption_reason": "",
        }

        if not self.ledger_path.exists():
            return summary

        with CrossProcessFileLock(self.lock_path):
            order_states: Dict[str, Dict[str, Any]] = {}
            seen_reserved: Set[str] = set()
            seen_submitted: Set[str] = set()

            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    for line_no, raw_line in enumerate(f, start=1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            if not isinstance(record, dict) or "event" not in record:
                                self._ledger_corrupted = True
                                self._ledger_corruption_reason = f"Malformed record structure at line {line_no}"
                                break

                            event = record.get("event")
                            data = record.get("data", {}) if isinstance(record.get("data"), dict) else {}
                            cl_ord_id = data.get("cl_ord_id")

                            if not cl_ord_id:
                                continue

                            if event == "ORDER_RESERVED":
                                if cl_ord_id in seen_reserved:
                                    self._ledger_corrupted = True
                                    self._ledger_corruption_reason = f"Duplicate reservation for {cl_ord_id!r} at line {line_no}"
                                    break
                                seen_reserved.add(cl_ord_id)
                                order_states[cl_ord_id] = {
                                    "state": OrderLifecycleState.RESERVED,
                                    "data": data,
                                    "line_no": line_no,
                                }

                            elif event in ("ORDER_SUBMITTED", "ORDER_PLACED"):
                                if cl_ord_id in seen_submitted:
                                    self._ledger_corrupted = True
                                    self._ledger_corruption_reason = f"Duplicate submission for {cl_ord_id!r} at line {line_no}"
                                    break
                                seen_submitted.add(cl_ord_id)
                                if cl_ord_id not in order_states:
                                    order_states[cl_ord_id] = {"data": data, "line_no": line_no}
                                order_states[cl_ord_id]["state"] = OrderLifecycleState.SUBMISSION_UNKNOWN

                            elif event in ("ORDER_RESTING", "ORDER_ACKNOWLEDGED"):
                                if cl_ord_id in order_states:
                                    order_states[cl_ord_id]["state"] = OrderLifecycleState.ACKNOWLEDGED
                                    order_states[cl_ord_id]["exchange_order_id"] = data.get("exchange_order_id")

                            elif event in ("RESTING_TIMEOUT_CANCEL_SENT", "CANCEL_REQUESTED"):
                                if cl_ord_id in order_states:
                                    order_states[cl_ord_id]["state"] = OrderLifecycleState.CANCEL_REQUESTED

                            elif event in ("ACK_TIMEOUT_AMBIGUOUS", "AMBIGUOUS_STATE"):
                                if cl_ord_id in order_states:
                                    order_states[cl_ord_id]["state"] = OrderLifecycleState.RECONCILIATION_REQUIRED

                            elif event in ("ORDER_TERMINAL", "ORDER_FILLED", "ORDER_CANCELLED"):
                                term_state = data.get("state", OrderLifecycleState.CANCELLED_CONFIRMED.value)
                                if term_state in (OrderLifecycleState.FILLED.value, "FILLED"):
                                    final_state = OrderLifecycleState.FILLED
                                else:
                                    final_state = OrderLifecycleState.CANCELLED_CONFIRMED
                                if cl_ord_id in order_states:
                                    order_states[cl_ord_id]["state"] = final_state

                        except Exception as parse_err:
                            self._ledger_corrupted = True
                            self._ledger_corruption_reason = f"Corrupted JSON at line {line_no}: {parse_err}"
                            break

            except Exception as io_err:
                self._ledger_corrupted = True
                self._ledger_corruption_reason = f"IO error during restart recovery: {io_err}"

            if self._ledger_corrupted:
                summary["ledger_corrupted"] = True
                summary["corruption_reason"] = self._ledger_corruption_reason
                return summary

            self._active_open_orders.clear()
            self._ambiguous_orders.clear()

            for cl_ord_id, info in order_states.items():
                st = info["state"]
                if st in (OrderLifecycleState.RESERVED, OrderLifecycleState.SUBMISSION_UNKNOWN, OrderLifecycleState.RECONCILIATION_REQUIRED):
                    self._ambiguous_orders[cl_ord_id] = {
                        "state": OrderLifecycleState.RECONCILIATION_REQUIRED,
                        "details": info["data"],
                    }
                    summary["ambiguous"].append(cl_ord_id)
                elif st in (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.CANCEL_REQUESTED):
                    self._active_open_orders[cl_ord_id] = {
                        "state": st,
                        "details": info["data"],
                    }
                    summary["active_open"].append(cl_ord_id)
                else:
                    summary["terminal"].append(cl_ord_id)

            summary["recovered_orders"] = len(order_states)
            return summary

    def register_order_reserved(self, cl_ord_id: str, details: Dict[str, Any]) -> None:
        """Register that an order has been allocated a persistent reservation slot."""
        self._active_open_orders[cl_ord_id] = {
            "state": OrderLifecycleState.RESERVED,
            "reservation_time": time.monotonic(),
            "details": details,
        }
        self.record_order_event_to_ledger("ORDER_RESERVED", {"cl_ord_id": cl_ord_id, **details})

    def register_order_submitted(self, cl_ord_id: str, details: Dict[str, Any]) -> None:
        """Register that an order has been dispatched and is awaiting acknowledgment."""
        self._active_open_orders[cl_ord_id] = {
            "state": OrderLifecycleState.SUBMISSION_UNKNOWN,
            "submission_time": time.monotonic(),
            "details": details,
        }
        self.record_order_event_to_ledger("ORDER_SUBMITTED", {"cl_ord_id": cl_ord_id, **details})

    def register_order_acknowledged(self, cl_ord_id: str, exchange_order_id: int | str) -> None:
        """Register that the order is resting on the order book."""
        if cl_ord_id in self._active_open_orders:
            self._active_open_orders[cl_ord_id]["state"] = OrderLifecycleState.ACKNOWLEDGED
            self._active_open_orders[cl_ord_id]["exchange_order_id"] = exchange_order_id
            self._active_open_orders[cl_ord_id]["resting_since"] = time.monotonic()
            self.record_order_event_to_ledger(
                "ORDER_RESTING",
                {"cl_ord_id": cl_ord_id, "exchange_order_id": exchange_order_id},
            )

    def register_ack_timeout(self, cl_ord_id: str) -> None:
        """Flag an order whose acknowledgment timed out (> 5.0s) as ambiguous."""
        if cl_ord_id in self._active_open_orders:
            order_data = self._active_open_orders.pop(cl_ord_id)
            order_data["state"] = OrderLifecycleState.RECONCILIATION_REQUIRED
            self._ambiguous_orders[cl_ord_id] = order_data
            self.record_order_event_to_ledger("ACK_TIMEOUT_AMBIGUOUS", {"cl_ord_id": cl_ord_id})

    def register_order_terminal(self, cl_ord_id: str, terminal_state: OrderLifecycleState, pnl_usd: Decimal = Decimal("0.0")) -> None:
        """Record order completion (filled, cancelled, rejected)."""
        if cl_ord_id in self._active_open_orders:
            del self._active_open_orders[cl_ord_id]
        if cl_ord_id in self._ambiguous_orders:
            del self._ambiguous_orders[cl_ord_id]
        self.record_order_event_to_ledger(
            "ORDER_TERMINAL",
            {"cl_ord_id": cl_ord_id, "state": terminal_state.value, "pnl_usd": str(pnl_usd)},
        )

    def handle_resting_timeout(self, cl_ord_id: str, elapsed_seconds: float) -> bool:
        """Evaluate 120s policy. Returns True if cancellation must be dispatched."""
        if elapsed_seconds >= self.scope.max_order_wait_seconds:
            if cl_ord_id in self._active_open_orders:
                self._active_open_orders[cl_ord_id]["state"] = OrderLifecycleState.CANCEL_REQUESTED
                self.record_order_event_to_ledger("RESTING_TIMEOUT_CANCEL_SENT", {"cl_ord_id": cl_ord_id})
            return True
        return False
