"""
====================================================
QuantEngine - Post-Cost Backtester with Friction Hurdle Gating
Phase 172 Implementation

Integrates FrictionHurdleGate into the historical backtester
pre-order decision boundary. Measures trade-selection effects,
fee impact, and net expectancy across execution styles (Taker vs Maker).
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Any

from backtesting.backtester import Backtester
from core.execution.friction_hurdle_gate import (
    evaluate_friction_hurdle,
    HurdleVerdict,
)
from core.execution.maker_execution_model import ExecutionStyle


@dataclass
class TradeSetupCandidate:
    setup_id: str
    symbol: str
    entry_price: Decimal
    target_price: Decimal
    stop_price: Decimal
    quantity: Decimal = Decimal("1")
    multiplier: Decimal = Decimal("0.001")
    entry_style: ExecutionStyle = ExecutionStyle.TAKER
    exit_style: ExecutionStyle = ExecutionStyle.TAKER
    risk_budget: Optional[Decimal] = None
    side: str = "BUY"


@dataclass
class TradeSelectionTally:
    total_candidates: int = 0
    rejected_fee_ratio: int = 0
    rejected_breakeven_multiple: int = 0
    rejected_post_fee_rr: int = 0
    rejected_multiple_rules: int = 0
    total_rejected: int = 0
    total_accepted: int = 0
    rejection_reasons: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "rejections": {
                "fee_ratio_exceeded_40pct": self.rejected_fee_ratio,
                "target_below_2x_breakeven": self.rejected_breakeven_multiple,
                "post_fee_rr_below_1_25": self.rejected_post_fee_rr,
                "multiple_rules_violated": self.rejected_multiple_rules,
            },
            "acceptance_rate_pct": round(
                (self.total_accepted / self.total_candidates * 100.0) if self.total_candidates > 0 else 0.0, 2
            ),
        }


class PostCostBacktester(Backtester):
    """
    Backtester extension with pre-order FrictionHurdleGate integration.
    Evaluates every candidate order against fee drag hurdles before execution.
    """

    def __init__(
        self,
        pipeline=None,
        event_bus=None,
        simulator=None,
        account=None,
        execution_style: ExecutionStyle = ExecutionStyle.TAKER,
        max_fee_ratio_pct: Decimal | float = Decimal("40.0"),
        min_post_fee_rr: Decimal | float = Decimal("1.25"),
        min_breakeven_multiple: Decimal | float = Decimal("2.0"),
        contract_multiplier: Decimal | float = Decimal("0.001"),
        initial_capital: Decimal | float = Decimal("10000.0"),
        **kwargs,
    ):
        if pipeline is not None and event_bus is not None and simulator is not None:
            super().__init__(pipeline, event_bus, simulator, account=account, **kwargs)
            self._prior_portfolio_gate = getattr(self, "portfolio_gate", None)
            self.portfolio_gate = self._friction_hurdle_gate_wrapper
        else:
            self.pipeline = pipeline
            self.event_bus = event_bus
            self.simulator = simulator
            self.account = account
            self._prior_portfolio_gate = None
        self.initial_capital = Decimal(str(initial_capital))
        self.execution_style = execution_style
        self.max_fee_ratio_pct = Decimal(str(max_fee_ratio_pct))
        self.min_post_fee_rr = Decimal(str(min_post_fee_rr))
        self.min_breakeven_multiple = Decimal(str(min_breakeven_multiple))
        self.contract_multiplier = Decimal(str(contract_multiplier))
        
        self.tally = TradeSelectionTally()
        self.verdicts: List[HurdleVerdict] = []

    def evaluate_candidate(self, candidate: TradeSetupCandidate) -> HurdleVerdict:
        """Evaluate a TradeSetupCandidate directly through the hurdle gate and stop risk budget."""
        if candidate.risk_budget is not None:
            from core.execution.maker_execution_model import audit_and_recalculate_stop_risk, TickRoundingPolicy
            risk_audit = audit_and_recalculate_stop_risk(
                entry_price=candidate.entry_price,
                raw_stop_price=candidate.stop_price,
                quantity=candidate.quantity,
                risk_budget=candidate.risk_budget,
                side=candidate.side,
                contract_multiplier=candidate.multiplier,
                policy=TickRoundingPolicy.CONSERVATIVE,
                estimated_entry_style=candidate.entry_style,
                estimated_exit_style=candidate.exit_style,
            )
            if not risk_audit.valid:
                self.tally.total_candidates += 1
                self.tally.total_rejected += 1
                reason = f"Stop risk budget breached: {risk_audit.rejection_reason}"
                self.tally.rejection_reasons.append(reason)
                v = HurdleVerdict(
                    allowed=False,
                    rejection_reason=reason,
                    execution_style=candidate.entry_style,
                    entry_price=candidate.entry_price,
                    target_price=candidate.target_price,
                    stop_price=risk_audit.normalized_stop_price if risk_audit.normalized_stop_price > Decimal("0") else candidate.stop_price,
                    target_points=abs(candidate.target_price - candidate.entry_price),
                    risk_points=abs(candidate.entry_price - candidate.stop_price),
                    gross_target_usd=Decimal("0"),
                    round_trip_fee_usd=Decimal("0"),
                    net_target_usd=Decimal("0"),
                    fee_to_target_pct=Decimal("100"),
                    post_fee_rr=Decimal("0"),
                    breakeven_points=Decimal("0"),
                )
                self.verdicts.append(v)
                return v

        self.tally.total_candidates += 1
        verdict = evaluate_friction_hurdle(
            entry_price=candidate.entry_price,
            target_price=candidate.target_price,
            stop_price=candidate.stop_price,
            quantity=candidate.quantity,
            contract_multiplier=candidate.multiplier,
            execution_style=candidate.entry_style,
            max_fee_ratio_pct=self.max_fee_ratio_pct,
            min_post_fee_rr=self.min_post_fee_rr,
            min_breakeven_margin_multiple=self.min_breakeven_multiple,
        )
        self.verdicts.append(verdict)
        if not verdict.allowed:
            self.tally.total_rejected += 1
            reason = verdict.rejection_reason or ""
            self.tally.rejection_reasons.append(reason)
            fails_fee_ratio = verdict.fee_to_target_pct > self.max_fee_ratio_pct
            fails_breakeven = verdict.target_points < (verdict.breakeven_points * self.min_breakeven_multiple)
            fails_rr = verdict.post_fee_rr < self.min_post_fee_rr
            fail_count = sum([fails_fee_ratio, fails_breakeven, fails_rr])
            if fail_count > 1:
                self.tally.rejected_multiple_rules += 1
            elif fails_fee_ratio:
                self.tally.rejected_fee_ratio += 1
            elif fails_breakeven:
                self.tally.rejected_breakeven_multiple += 1
            elif fails_rr:
                self.tally.rejected_post_fee_rr += 1
        else:
            self.tally.total_accepted += 1
        return verdict

    def _friction_hurdle_gate_wrapper(self, order) -> bool:
        """Evaluate friction hurdle right before trade execution."""
        self.tally.total_candidates += 1
        
        entry = getattr(order, "entry", None)
        target = getattr(order, "take_profit", None)
        stop = getattr(order, "stop_loss", None)
        quantity = getattr(order, "quantity", Decimal("1"))
        
        if entry is None or target is None or stop is None:
            # Fall back to prior gate if order does not have price targets
            if self._prior_portfolio_gate:
                return self._prior_portfolio_gate(order)
            return True

        verdict = evaluate_friction_hurdle(
            entry_price=Decimal(str(entry)),
            target_price=Decimal(str(target)),
            stop_price=Decimal(str(stop)),
            quantity=Decimal(str(quantity)),
            contract_multiplier=self.contract_multiplier,
            execution_style=self.execution_style,
            max_fee_ratio_pct=self.max_fee_ratio_pct,
            min_post_fee_rr=self.min_post_fee_rr,
            min_breakeven_margin_multiple=self.min_breakeven_multiple,
        )
        self.verdicts.append(verdict)

        if not verdict.allowed:
            self.tally.total_rejected += 1
            reason = verdict.rejection_reason or ""
            self.tally.rejection_reasons.append(reason)
            
            # Categorize failure rules
            fails_fee_ratio = verdict.fee_to_target_pct > self.max_fee_ratio_pct
            fails_breakeven = verdict.target_points < (verdict.breakeven_points * self.min_breakeven_multiple)
            fails_rr = verdict.post_fee_rr < self.min_post_fee_rr

            fail_count = sum([fails_fee_ratio, fails_breakeven, fails_rr])
            if fail_count > 1:
                self.tally.rejected_multiple_rules += 1
            elif fails_fee_ratio:
                self.tally.rejected_fee_ratio += 1
            elif fails_breakeven:
                self.tally.rejected_breakeven_multiple += 1
            elif fails_rr:
                self.tally.rejected_post_fee_rr += 1
            
            return False

        self.tally.total_accepted += 1
        
        # If user also specified a custom portfolio gate, check it
        if self._prior_portfolio_gate:
            return self._prior_portfolio_gate(order)
        return True

    def get_selection_report(self) -> Dict[str, Any]:
        """Produce comprehensive trade selection report."""
        rep = self.tally.summary()
        rep["execution_style"] = self.execution_style.value
        rep["max_fee_ratio_pct"] = str(self.max_fee_ratio_pct)
        rep["min_post_fee_rr"] = str(self.min_post_fee_rr)
        rep["min_breakeven_multiple"] = str(self.min_breakeven_multiple)
        return rep
