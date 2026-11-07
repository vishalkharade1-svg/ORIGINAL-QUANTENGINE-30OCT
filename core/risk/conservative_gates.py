"""Conservative fail-closed risk corrections (Phase 7 local track).

INTEGRATION STATUS (forensically pinned 2026-09-22): DEFINED + UNIT-TESTED,
NOT WIRED. No production, paper, backtest, or live caller invokes any
symbol in this module (see ``tests/test_authoritative_path_phase7.py``
boundary pins for the equivalent economics/contract gates). The live
production gates are ``core/setup/decision_engine.py`` (confidence,
R:R) and ``core/risk/risk_engine.py`` (geometry, R:R revalidation,
kill switch, loss limits, exposure ceiling). Do NOT cite this module
as production protection until a caller is wired AND an integration
test proves the executable path reaches it.

Additive authoritative gates; existing engine behavior is intentionally
untouched this session because pinned tests assert current values
(see blockers at the bottom).  New promotion/production paths must consult
these gates:

* ``check_confidence`` — the authoritative minimum is 80
  (``config/risk_settings.py::MIN_CONFIDENCE``).  Phase-4 CORRECTED:
  ``DecisionEngine`` carries NO ``MIN_CONFIDENCE`` shadow (verified:
  ``hasattr(DecisionEngine, "MIN_CONFIDENCE")`` is False and
  ``analyze()`` reads ``risk_settings.MIN_CONFIDENCE`` per candidate).
  Any older note claiming a live 70 pre-filter is STALE documentation,
  not an active code defect.
* ``check_exposure`` — total notional vs equity against an explicit cap.
  The legacy ``MAX_TOTAL_EXPOSURE_PCT = 25.0`` default is dangerously
  permissive and is NOT reused here; callers pass an explicit cap and the
  conservative default is 100% of equity.
* ``check_leverage`` / ``check_margin`` — explicit notional and margin
  affordability checks against verified contract terms.
* ``BalanceDivergenceHalt`` — halts new risk when the local ledger diverges
  from exchange-reported equity beyond tolerance.  Exchange state is
  authoritative.
* ``PortfolioExposure`` — portfolio-level notional aggregation with a
  fail-closed cap.

Blockers (NOT changed this session; would break pinned tests that can not
be re-verified while the execution shell is unavailable):

* ``core/setup/decision_engine.py`` — HISTORICALLY a ``MIN_CONFIDENCE = 70``
  shadow vs ``config/risk_settings.py`` — ``MIN_CONFIDENCE = 80``.  PHASE-4
  CORRECTED (closed, not open): the shadow was removed and
  ``tests/test_open_blockers_phase3.py::test_confidence_shadow_closed``
  pins its absence.  Listed here only as provenance; there is no
  remaining 70-shadow to fix.
* ``core/risk/position_size.py:85`` — ``PositionSize.risk_reward`` returns
  ``position_value / expected_loss`` (a notional multiple), NOT
  reward/risk.  Pinned by ``tests/test_hardening_stage123.py:412``.
  Fix = rename to ``notional_to_risk`` plus a separately computed
  ``reward_to_risk`` from entry/stop/target, then update the pin.
* ``PositionManager.manage_into(equity)`` exists
  (``core/risk/position_manager.py:297``) but no production caller passes
  live equity; integration is pending the verified runtime wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field


AUTHORITATIVE_MIN_CONFIDENCE = 80
CONSERVATIVE_MAX_EXPOSURE_PCT = 1.0


@dataclass(frozen=True, slots=True)
class RiskVerdict:
    allowed: bool
    reason: str


def check_confidence(confidence: float) -> RiskVerdict:
    """Enforce the authoritative minimum confidence of 80, fail-closed."""
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return RiskVerdict(False, "CONFIDENCE_NOT_NUMERIC")
    if value != value:
        return RiskVerdict(False, "CONFIDENCE_NON_FINITE")
    if value < AUTHORITATIVE_MIN_CONFIDENCE:
        return RiskVerdict(
            False,
            "CONFIDENCE_%s_BELOW_AUTHORITATIVE_MINIMUM_%s"
            % (value, AUTHORITATIVE_MIN_CONFIDENCE))
    return RiskVerdict(True, "CONFIDENCE_ACCEPTED")


def check_exposure(*, notional: float, equity: float,
                   max_exposure_pct: float = CONSERVATIVE_MAX_EXPOSURE_PCT,
                   ) -> RiskVerdict:
    """Refuse unresolved notional above the explicit cap (default: 1x equity)."""
    try:
        amount = float(notional)
        funds = float(equity)
        cap = float(max_exposure_pct)
    except (TypeError, ValueError):
        return RiskVerdict(False, "EXPOSURE_INPUT_NOT_NUMERIC")
    if (amount != amount or funds != funds or cap != cap
            or amount < 0 or funds <= 0 or cap < 0):
        return RiskVerdict(False, "EXPOSURE_INPUT_INVALID")
    if amount > funds * cap:
        return RiskVerdict(
            False,
            "EXPOSURE_%.2f_EXCEEDS_CAP_%.2f_OF_EQUITY_%.2f"
            % (amount, cap, funds))
    return RiskVerdict(True, "EXPOSURE_ACCEPTED")


def check_leverage(*, notional: float, equity: float,
                   max_leverage: float) -> RiskVerdict:
    """Refuse notional beyond max_leverage x equity."""
    try:
        lev = float(max_leverage)
    except (TypeError, ValueError):
        return RiskVerdict(False, "LEVERAGE_NOT_NUMERIC")
    if lev != lev or lev <= 0:
        return RiskVerdict(False, "LEVERAGE_INVALID")
    return check_exposure(notional=notional, equity=equity,
                          max_exposure_pct=lev)


def check_margin(*, margin_required: float, equity: float) -> RiskVerdict:
    """Refuse orders whose margin exceeds available equity."""
    try:
        required = float(margin_required)
        funds = float(equity)
    except (TypeError, ValueError):
        return RiskVerdict(False, "MARGIN_INPUT_NOT_NUMERIC")
    if (required != required or funds != funds
            or required < 0 or funds < 0):
        return RiskVerdict(False, "MARGIN_INPUT_INVALID")
    if required > funds:
        return RiskVerdict(False, "MARGIN_EXCEEDS_EQUITY")
    return RiskVerdict(True, "MARGIN_ACCEPTED")


@dataclass
class BalanceDivergenceHalt:
    """Halt new risk while local and exchange equity diverge.

    Exchange/private state is authoritative.  ``note_divergence`` latches the
    halt; only an explicit operator ``resolve`` clears it — profitable fills
    must never auto-clear a balance disagreement.

    Phase-13 authority adjudication (§16): LOCAL-TRACK / UNWIRED —
    this class DUPLICATES the production reconciliation authority
    (``core/live/reconciler.py::Reconciler``, which IS wired into
    ``BrokerEngine`` with startup + runtime halts).  There is
    exactly ONE mandatory balance-divergence authority (the
    Reconciler); this class is retained as a tested local-track
    primitive and must never be described as production
    protection.  Integration would create two competing
    reconciliation authorities and is explicitly rejected.
    """

    tolerance_pct: float = 0.01
    halted: bool = False
    last_reason: str = ""

    def note_divergence(self, *, local_equity: float,
                        exchange_equity: float) -> RiskVerdict:
        try:
            local = float(local_equity)
            remote = float(exchange_equity)
        except (TypeError, ValueError):
            self.halted = True
            self.last_reason = "BALANCE_DIVERGENCE_UNMEASURABLE"
            return RiskVerdict(False, self.last_reason)
        if remote <= 0 or local != local or remote != remote:
            self.halted = True
            self.last_reason = "BALANCE_DIVERGENCE_UNMEASURABLE"
            return RiskVerdict(False, self.last_reason)
        drift = abs(local - remote) / remote
        if drift > self.tolerance_pct:
            self.halted = True
            self.last_reason = (
                "BALANCE_DIVERGENCE_HALT_drift_%.4f_exceeds_%.4f"
                % (drift, self.tolerance_pct))
            return RiskVerdict(False, self.last_reason)
        return RiskVerdict(True, "BALANCES_RECONCILED")

    def resolve(self, *, operator: str) -> None:
        if not operator:
            raise ValueError("operator identity is required to resolve a halt")
        self.halted = False
        self.last_reason = ""


@dataclass
class PortfolioExposure:
    """Portfolio-level notional cap across symbols, fail-closed."""

    max_exposure_pct: float = CONSERVATIVE_MAX_EXPOSURE_PCT
    notionals: dict = field(default_factory=dict)

    def reserve(self, key: str, notional: float, equity: float) -> RiskVerdict:
        try:
            amount = float(notional)
        except (TypeError, ValueError):
            return RiskVerdict(False, "NOTIONAL_NOT_NUMERIC")
        if amount != amount or amount < 0:
            return RiskVerdict(False, "NOTIONAL_INVALID")
        total = sum(self.notionals.values()) + amount
        verdict = check_exposure(notional=total, equity=equity,
                                 max_exposure_pct=self.max_exposure_pct)
        if not verdict.allowed:
            return RiskVerdict(
                False, "PORTFOLIO_" + verdict.reason)
        self.notionals[key] = self.notionals.get(key, 0.0) + amount
        return RiskVerdict(True, "PORTFOLIO_EXPOSURE_ACCEPTED")

    def release(self, key: str) -> None:
        self.notionals.pop(key, None)
