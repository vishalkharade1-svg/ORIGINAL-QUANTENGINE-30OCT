"""
====================================================

QuantEngine

LIVE Safety Gate (Phase 11A)

The ONE centralized, fail-closed LIVE execution safety
boundary. Every production path that can place a real
order must go through this gate:

    Signal
      -> Risk
        -> OrderIntent
          -> LiveSafetyGate.require(...)   <-- HERE
            -> authenticated live executor
              -> exchange order endpoint

LIVE execution requires ALL of (no single-flag bypass):

    execution mode == LIVE
    ALLOW_LIVE == true
    LIVE_EXECUTE == true
    valid authenticated Delta credentials

Covered exchange WRITES: order placement (DeltaOrderExecutor.
execute) AND order cancellation (DeltaOrderExecutor.cancel
-- killing a working bracket can leave a position naked).
Reads (fetch/balance/positions) are auth-guarded at the
transport, not safety-gated: they cannot move money.

If ANY condition is missing the gate refuses with the
typed LiveBlockedError and the exchange transport MUST
NOT be called (callers enforce the gate BEFORE any
transport write; see DeltaOrderExecutor.execute and
BrokerEngine._route).

UNKNOWN / INVALID / CONFLICTING modes are rejected with
the typed ConfigurationError -- never silently
downgraded to PAPER and never silently fallen through
to analyze-only.

HARD RULES for this module:

  * Pure decision logic: decide() takes explicit
    parameters and returns a SafetyDecision. No network,
    no exchange objects, no strategy state.
  * stdlib only. No secrets are ever logged, echoed in
    reasons, or included in audit events -- reasons name
    only the missing CONDITIONS (e.g. "ALLOW_LIVE=false").
  * The gate is an ADDITIONAL layer. The existing
    DeltaExchange._require_auth() fail-closed behavior is
    preserved underneath (defense in depth).

====================================================
"""

from dataclasses import dataclass
from dataclasses import field

import secrets

from core.common.logging_config import get_logger

log = get_logger(__name__)

_AUDIT_COMPONENT = "LiveSafetyGate"

# Per-process mint secret (hardening: a SafetyDecision is only
# arming if THIS process's decide() minted it). decide() stamps
# every verdict with _MINT; require_decision() refuses any token
# carrying a different (or missing) stamp — including a
# hand-constructed SafetyDecision(allowed=True, mode="LIVE")
# built to look armed. The secret is never logged, never
# serialized, and never leaves the process.
_MINT = secrets.token_hex(16)


# ==================================================
# Typed errors
# ==================================================


class LiveSafetyError(RuntimeError):

    """Base for every Phase 11A safety refusal."""


class LiveBlockedError(LiveSafetyError):

    """LIVE execution refused: at least one arming
    condition is missing. Fail closed -- the caller must
    NOT touch the exchange transport."""


class ConfigurationError(LiveSafetyError):

    """Execution-mode configuration is unknown, invalid,
    or conflicting (e.g. PAPER+LIVE both enabled). The
    operator must fix configuration; nothing starts."""


# ==================================================
# Explicit execution mode
# ==================================================


class ExecutionMode:

    """Typed execution-mode representation.

    Only two production modes exist: PAPER and LIVE.
    ANALYZE is the explicit no-fills application state
    (live data, engines run, nothing is booked or
    placed). Anything else is rejected -- there is no
    silent `else: analyze_only()` fall-through.
    """

    PAPER = "PAPER"

    LIVE = "LIVE"

    ANALYZE = "ANALYZE"

    VALID = frozenset({PAPER, LIVE, ANALYZE})

    # -------------------------------------------------

    @staticmethod
    def _as_bool(name, value):
        """Strict boolean coercion for mode flags.

        Real bools pass through. Strings accept only the
        unambiguous spellings; anything else is a
        configuration error (never silently False).
        """

        if isinstance(value, bool):
            return value

        if value is None:
            return False

        text = str(value).strip().lower()

        if text in ("1", "true", "yes", "on"):
            return True

        if text in ("", "0", "false", "no", "off"):
            return False

        raise ConfigurationError(
            "Invalid boolean for {}: {!r} "
            "(expected true/false).".format(name, value)
        )

    # -------------------------------------------------

    @classmethod
    def resolve(
        cls,
        paper_mode=False,
        live_mode=False,
        execution_mode="",
    ):
        """Resolve the effective mode or raise.

        Rules:

          * PAPER_MODE and LIVE_MODE both enabled ->
            ConfigurationError (conflicting; PAPER must
            NOT silently win).
          * An explicit EXECUTION_MODE override, when
            set, must name PAPER / LIVE / ANALYZE or a
            ConfigurationError is raised. The override
            is authoritative over the single flags.
          * Otherwise PAPER flag -> PAPER, LIVE flag ->
            LIVE, neither -> ANALYZE.
        """

        paper = cls._as_bool("PAPER_MODE", paper_mode)

        live = cls._as_bool("LIVE_MODE", live_mode)

        if paper and live:
            raise ConfigurationError(
                "Conflicting execution modes: PAPER_MODE "
                "and LIVE_MODE cannot both be enabled."
            )

        override = (
            str(execution_mode).strip().upper()
            if execution_mode is not None
            else ""
        )

        if override:
            if override not in cls.VALID:
                raise ConfigurationError(
                    "Invalid EXECUTION_MODE={!r}: expected "
                    "one of PAPER, LIVE, ANALYZE.".format(
                        execution_mode
                    )
                )

            return override

        if paper:
            return cls.PAPER

        if live:
            return cls.LIVE

        return cls.ANALYZE


# ==================================================
# Safety decision (explicit arming token)
# ==================================================


@dataclass(frozen=True)
class SafetyDecision:

    """Immutable verdict of one gate evaluation.

    An `allowed == True` decision is the explicit arming
    token a live consumer (BrokerEngine, DeltaOrder
    Executor, main.py) must hold. It carries NO secrets --
    only the mode, the evaluated conditions, and the
    human-readable refusal reason.

    Hardening: `allowed` alone never arms anything. Only a
    token minted by this process's decide() (matching the
    private `_mint` stamp) AND re-evaluating to allowed
    from its own fields passes require_decision().
    Hand-constructed or dataclasses.replace()-edited tokens
    are refused even when their `allowed` flag reads True.
    """

    allowed: bool

    mode: str

    reason: str

    allow_live: bool = False

    live_execute: bool = False

    has_credentials: bool = False

    # Private mint stamp. compare=False so operational
    # equality ("same verdict") is unaffected; the stamp is
    # checked by identity in require_decision(), never shown.
    _mint: str = field(default="", repr=False, compare=False)

    # -------------------------------------------------

    @property
    def armed(self):
        """Alias operators/tests read naturally."""

        return self.allowed


# ==================================================
# The gate
# ==================================================


class LiveSafetyGate:

    """Centralized LIVE execution safety boundary."""

    MODE = ExecutionMode.PAPER

    # -------------------------------------------------

    @staticmethod
    def _has_credentials(api_key=None, api_secret=None,
                         has_credentials=None):
        """Credential presence WITHOUT touching secrets.

        An explicit `has_credentials` verdict wins (lets
        callers use the exchange's own `authenticated`
        property). Otherwise presence = both key and
        secret are non-empty. Values are never logged.
        """

        if has_credentials is not None:
            return bool(has_credentials)

        try:
            return bool(
                (api_key or "") and (api_secret or "")
            )
        except Exception:
            return False

    # -------------------------------------------------

    @classmethod
    def decide(
        cls,
        *,
        mode=ExecutionMode.PAPER,
        allow_live=False,
        live_execute=False,
        api_key=None,
        api_secret=None,
        has_credentials=None,
    ):
        """Pure gate evaluation. Never raises for a
        refused mode -- returns `allowed=False` with the
        reason naming every missing condition. Raises
        ConfigurationError ONLY for an unknown mode
        string (fail closed on invalid input)."""

        normalized = (
            str(mode).strip().upper()
            if mode is not None
            else ""
        )

        if normalized not in ExecutionMode.VALID:
            raise ConfigurationError(
                "Invalid execution mode={!r}: expected "
                "one of PAPER, LIVE, ANALYZE.".format(mode)
            )

        allow = bool(allow_live)

        execute = bool(live_execute)

        creds = cls._has_credentials(
            api_key=api_key,
            api_secret=api_secret,
            has_credentials=has_credentials,
        )

        if normalized != ExecutionMode.LIVE:
            return SafetyDecision(
                allowed=False,
                mode=normalized,
                reason=(
                    "mode is {}, not LIVE".format(normalized)
                ),
                allow_live=allow,
                live_execute=execute,
                has_credentials=creds,
                _mint=_MINT,
            )

        missing = []

        if not allow:
            missing.append("ALLOW_LIVE=false")

        if not execute:
            missing.append("LIVE_EXECUTE=false")

        if not creds:
            missing.append("credentials missing")

        if missing:
            return SafetyDecision(
                allowed=False,
                mode=normalized,
                reason=(
                    "LIVE blocked: "
                    + ", ".join(missing)
                ),
                allow_live=allow,
                live_execute=execute,
                has_credentials=creds,
                _mint=_MINT,
            )

        return SafetyDecision(
            allowed=True,
            mode=normalized,
            reason="LIVE armed: all conditions satisfied",
            allow_live=True,
            live_execute=True,
            has_credentials=True,
            _mint=_MINT,
        )

    # -------------------------------------------------

    @classmethod
    def require(
        cls,
        *,
        mode=ExecutionMode.PAPER,
        allow_live=False,
        live_execute=False,
        api_key=None,
        api_secret=None,
        has_credentials=None,
        component="unknown",
    ):
        """Enforce the gate: return the armed decision or
        raise LiveBlockedError. Emits the audit event for
        BOTH outcomes (armed and blocked)."""

        decision = cls.decide(
            mode=mode,
            allow_live=allow_live,
            live_execute=live_execute,
            api_key=api_key,
            api_secret=api_secret,
            has_credentials=has_credentials,
        )

        if not decision.allowed:
            log.warning(
                "LIVE_EXECUTION_BLOCKED mode=%s reason=%s "
                "component=%s",
                decision.mode,
                decision.reason,
                component,
            )

            raise LiveBlockedError(
                "LIVE EXECUTION REFUSED ({}): {}".format(
                    component, decision.reason
                )
            )

        log.warning(
            "LIVE_EXECUTION_ARMED mode=%s component=%s",
            decision.mode,
            component,
        )

        return decision

    # -------------------------------------------------

    @classmethod
    def require_decision(cls, decision, component="unknown"):
        """Enforce a pre-computed decision object (the
        arming token consumers carry). Passes ONLY a token
        minted by this process's decide() whose own fields
        re-evaluate to allowed. Refuses, with
        LiveBlockedError, ALL of: non-decisions, None, refused
        tokens, hand-constructed tokens (wrong/missing mint
        stamp -- even a fully consistent-looking
        SafetyDecision(allowed=True, mode="LIVE", ...) built
        by hand), and dataclasses.replace()-edited tokens
        whose fields no longer re-evaluate to allowed."""

        if not isinstance(decision, SafetyDecision):
            return cls._refuse_decision(
                decision, "no armed safety decision provided",
                component,
            )

        if decision._mint != _MINT:
            return cls._refuse_decision(
                decision,
                "decision was not minted by LiveSafetyGate.decide "
                "(fabricated token)",
                component,
            )

        re_evaluated = cls.decide(
            mode=decision.mode,
            allow_live=decision.allow_live,
            live_execute=decision.live_execute,
            has_credentials=decision.has_credentials,
        )

        if not re_evaluated.allowed:
            return cls._refuse_decision(
                decision,
                "decision fields re-evaluate to refused: "
                + re_evaluated.reason,
                component,
            )

        if not (decision.allowed and decision.mode == ExecutionMode.LIVE):
            return cls._refuse_decision(
                decision,
                "decision flag/mode inconsistent with an armed "
                "verdict: {}".format(decision.reason),
                component,
            )

        return decision

    @classmethod
    def _refuse_decision(cls, decision, reason, component="unknown"):
        """Shared fail-closed refusal with audit logging."""

        log.warning(
            "LIVE_EXECUTION_BLOCKED mode=%s reason=%s "
            "component=%s",
            (
                decision.mode
                if isinstance(decision, SafetyDecision)
                else "UNKNOWN"
            ),
            reason,
            component,
        )

        raise LiveBlockedError(
            "LIVE EXECUTION REFUSED ({}): {}".format(
                component, reason
            )
        )

    # -------------------------------------------------

    @classmethod
    def from_settings(cls, settings_obj=None, *, mode=None,
                      api_key=None, api_secret=None):
        """Build the gate inputs from operator settings.

        Prefers explicit overrides (tests, main.py) and
        otherwise reads ALLOW_LIVE / LIVE_EXECUTE /
        DELTA_API_KEY / DELTA_API_SECRET plus the mode
        flags (PAPER_MODE / LIVE_MODE / EXECUTION_MODE).
        Raises ConfigurationError on conflicting or
        unknown mode configuration.
        """

        if settings_obj is None:
            from config.settings import settings as settings_obj

        allow = bool(getattr(settings_obj, "ALLOW_LIVE", False))

        execute = bool(
            getattr(settings_obj, "LIVE_EXECUTE", False)
        )

        if mode is None:
            mode = ExecutionMode.resolve(
                paper_mode=getattr(
                    settings_obj, "PAPER_MODE", False
                ),
                live_mode=getattr(
                    settings_obj, "LIVE_MODE", False
                ),
                execution_mode=getattr(
                    settings_obj, "EXECUTION_MODE", ""
                ),
            )

        key = (
            api_key
            if api_key is not None
            else getattr(settings_obj, "API_KEY", "")
        )

        secret = (
            api_secret
            if api_secret is not None
            else getattr(settings_obj, "API_SECRET", "")
        )

        return {
            "mode": mode,
            "allow_live": allow,
            "live_execute": execute,
            "api_key": key,
            "api_secret": secret,
        }

    # -------------------------------------------------

    @classmethod
    def test_armed(cls):
        """Explicit arming token for OFFLINE unit tests
        with fake transports. Never touches real settings
        or real credentials. Production code MUST NOT
        call this -- main.py arms via from_settings +
        require over operator configuration."""

        return cls.decide(
            mode=ExecutionMode.LIVE,
            allow_live=True,
            live_execute=True,
            has_credentials=True,
        )

    # -------------------------------------------------

    @staticmethod
    def describe(decision):
        """Operator-safe safety-state snapshot (no
        secrets): EXECUTION MODE + LIVE EXECUTION
        BLOCKED/ARMED + reason."""

        if not isinstance(decision, SafetyDecision):
            return {
                "execution_mode": "UNKNOWN",
                "live_execution": "BLOCKED",
                "reason": (
                    "no safety decision available"
                ),
            }

        return {
            "execution_mode": decision.mode,
            "live_execution": (
                "ARMED" if decision.allowed else "BLOCKED"
            ),
            "reason": decision.reason,
        }

    # -------------------------------------------------

    @classmethod
    def format_banner(cls, decision):
        """Startup safety banner lines (safe to print and
        to store in evidence)."""

        state = cls.describe(decision)

        return [
            "EXECUTION MODE: {}".format(
                state["execution_mode"]
            ),
            "LIVE EXECUTION: {}".format(
                state["live_execution"]
            ),
            "LIVE SAFETY: {}".format(state["reason"]),
        ]
