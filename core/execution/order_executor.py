"""
====================================================

Delta Order Executor

Maps a risk-validated OrderIntent (produced by RiskEngine
into context.order) into a Delta order payload and places it
through a DeltaExchange instance.

This is the execution half of the
Setup -> Decision -> Signal -> Risk -> Order Intent ->
Execution Adapter flow: the backtester consumes the same
OrderIntent via TradeSimulator, so Replay, Paper and Live
all share one intent contract.

The conversation thread expects the caller to provide a
ContractRegistry (from DeltaContractLoader().load()); the
registry carries the Delta product_id + price/quantity
precision needed to build a valid /v2/orders payload.

====================================================
"""

from core.exchanges.delta.delta_exchange import DeltaExchange

from core.exchanges.delta.write_authority import token_for_live_safety

from core.execution.live_safety_gate import LiveSafetyGate

from core.risk.costs import post_cost_rr

import math
from decimal import Decimal, InvalidOperation


class InvalidContractError(ValueError):

    """Contract metadata is missing or unusable for a live
    payload (unknown symbol, missing/non-numeric/zero
    product_id, or invalid price/quantity precision).
    Raised BEFORE any transport call."""


class _ClientOrderSeq:
    """Process-scoped monotonic counter (Phase 12).

    Deterministic fallback uniqueness for client order ids:
    no wall clock, no UUIDs, no randomness. The primary id
    derives from the registry-minted order_id (setup-bound);
    this counter only fires when an intent carries no
    order_id (hand-built/test paths).
    """

    def __init__(self):
        self.value = 0

    def next(self):
        self.value += 1
        return self.value


_CLIENT_ORDER_SEQ = _ClientOrderSeq()


def order_seq_value():
    """Current fallback-sequence value (journal persistence)."""

    return _CLIENT_ORDER_SEQ.value


def reset_order_seq(value=0):
    """Reset the fallback counter (tests / restart seeding)."""

    _CLIENT_ORDER_SEQ.value = max(0, int(value))


class DeltaOrderExecutor:

    # Capability marker consumed by BrokerEngine: this
    # executor enforces the Phase 11A LiveSafetyGate
    # inside execute() and therefore accepts the explicit
    # `safety` arming token.
    supports_safety = True

    def __init__(
        self,
        exchange,
        registry,
        attach_brackets=True,
        order_id_factory=None,
    ):

        if not isinstance(exchange, DeltaExchange):
            exchange = DeltaExchange(rest=exchange)

        self.exchange = exchange

        self.registry = registry

        self.attach_brackets = attach_brackets

        self.order_id_factory = (
            order_id_factory
            or self._default_client_order_id
        )

    # -------------------------------------------------

    @staticmethod
    def _default_client_order_id(intent):

        # Phase 12 deterministic client order id (no wall
        # clock): the registry-minted order_id is setup-bound
        # and unique per setup per run, so it is the primary
        # id. Sanitized to venue-safe characters; the
        # monotonic fallback fires only when no order_id is
        # present. Scope: unique per setup per engine process;
        # a restarted process re-mints per-run ids, so the
        # reconciler journal (open_order_id) remains the
        # cross-restart authority -- see the restart hazard
        # note in the Phase 12 report.
        order_id = getattr(intent, "order_id", "") or ""

        if order_id:

            safe = "".join(
                ch if (ch.isalnum() or ch in "-_.:")
                else "-"
                for ch in str(order_id)
            )[:64] or "ORDER"

            return f"QE-{safe}"

        return (
            f"QE-{intent.symbol}-{_CLIENT_ORDER_SEQ.next()}"
        )

    # -------------------------------------------------

    def execute(self, intent, *, safety=None):
        """
        Validate the intent, enforce the Phase 11A LIVE
        safety gate, build the Delta payload and place
        the order. Returns the exchange response plus the
        payload sent (useful for audit trails / the ledger).

        Safety order (all fail closed, zero transport
        before the gate passes):

          1. invalid intent -> {"success": False} (no call)
          2. unknown/invalid contract -> InvalidContractError
          3. cost-aware economics refusal -> {"success": False}
             (post-cost R:R enforced when costs are nonzero;
             non-finite costs always fail closed; vacuous at
             zero costs where gross gating is RiskEngine's
             plus the broker route's wired duty)
          4. gate refused -> LiveBlockedError (no call)
          5. transport via exchange.place_order (which keeps
             its own _require_auth defense-in-depth guard)
          6. payload revalidation: the venue-rounded size/price
             are re-parsed and must not silently invalidate the
             sizing decision (size never increased, minimum
             honored, price on the tick grid) or the write is
             refused via InvalidContractError.

        `safety` is an armed SafetyDecision (see
        LiveSafetyGate.require / test_armed). When None the
        gate is evaluated from operator settings plus the
        bound exchange's credentials -- with default
        settings (ALLOW_LIVE=false) that raises
        LiveBlockedError.
        """

        if not intent.valid:

            return {
                "success": False,
                "reason": (
                    intent.reason or "invalid order intent"
                ),
            }

        contract = self._contract(intent)

        economics_refusal = self._refuse_uneconomic(intent)

        if economics_refusal is not None:

            return {
                "success": False,
                "reason": economics_refusal,
            }

        if safety is None:

            # Resolve the configured mode instead of forcing LIVE.
            # A live executor must not override PAPER_MODE/ANALYZE or
            # bypass conflicting execution-mode configuration.
            gate_inputs = LiveSafetyGate.from_settings(
                api_key=getattr(
                    self.exchange, "api_key", None
                ),
                api_secret=getattr(
                    self.exchange, "api_secret", None
                ),
            )

            safety = LiveSafetyGate.require(
                component="DeltaOrderExecutor.execute",
                **gate_inputs,
            )
        else:

            safety = LiveSafetyGate.require_decision(
                safety,
                component="DeltaOrderExecutor.execute",
            )

        self._require_execution_evidence(contract, intent.symbol)

        payload = self._validated_payload(intent, contract)

        base_url = getattr(self.exchange.rest, "base_url", None)
        authority = token_for_live_safety(
            safety, base_url=base_url, endpoint="/v2/orders", payload=payload
        )

        response = self.exchange.place_order(payload, authority=authority)

        return {
            "success": True,
            "intent": intent,
            "contract": contract,
            "payload": payload,
            "response": response,
        }

    # --------------------------------------------------

    @staticmethod
    def _refuse_uneconomic(intent):
        """Cost-aware economics gate (Phase 14 live boundary).

        Returns a refusal reason string, or None when the fill
        economics are acceptable. Layering (explicit, identical
        to the TradeSimulator choke): gross geometry + R:R are
        RiskEngine's wired duty upstream (plus the broker-route
        gates), enforced against the active minimum-R policy;
        THIS layer validates only what costs change.
        Zero costs (commission == 0 and slippage == 0) leave
        behavior byte-identical — the gate is vacuous, so
        test-harness and legacy direct calls are unaffected.
        Nonzero costs shift the entry adversely (symmetric) and
        post-cost R:R below the active minimum-R policy refuses
        via the single authority; non-finite costs ALWAYS fail
        closed.
        Pure read-only check: never mutates the intent, never
        touches transport.
        """
        try:
            direction = str(getattr(intent, "direction", "") or "")
            entry = float(getattr(intent, "entry", 0.0) or 0.0)
            stop = float(getattr(intent, "stop_loss", 0.0) or 0.0)
            target = float(getattr(intent, "take_profit", 0.0) or 0.0)
            quantity = float(getattr(intent, "quantity", 0.0) or 0.0)
            exit_mode = str(getattr(intent, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET) or risk_settings.EXIT_MODE_FIXED_TARGET).upper()
            commission = float(
                getattr(intent, "commission", 0.0) or 0.0)
            slippage = float(
                getattr(intent, "slippage", 0.0) or 0.0)
            symbol = str(getattr(intent, "symbol", "") or "")
        except (TypeError, ValueError):
            return "non-finite order economics"

        if not (math.isfinite(commission)
                and math.isfinite(slippage)):
            return "non-finite order costs"

        if exit_mode == risk_settings.EXIT_MODE_TRAILING_STOP:
            return "trailing-stop execution contract unavailable"

        if commission == 0.0 and slippage == 0.0:
            return None

        verdict = post_cost_rr(
            direction=direction,
            entry=entry,
            stop=stop,
            target=target,
            quantity=quantity,
            commission=commission,
            slippage=slippage,
            symbol=symbol,
        )
        if not verdict.allowed:
            return verdict.reason
        return None

    # -------------------------------------------------

    def _contract(self, intent):

        contract = self.registry.get(intent.symbol)

        if contract is None:

            raise InvalidContractError(
                f"no contract for symbol "
                f"{intent.symbol!r} (load DeltaContractLoader "
                f"first)"
            )

        try:
            product_id_decimal = Decimal(str(contract.product_id))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} "
                f"has non-numeric product_id "
                f"{contract.product_id!r}"
            ) from exc

        if (not product_id_decimal.is_finite()
                or product_id_decimal != product_id_decimal.to_integral_value()):
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} has non-integer "
                f"product_id {contract.product_id!r}"
            )
        product_id = int(product_id_decimal)

        if product_id <= 0:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} "
                f"has invalid product_id "
                f"{contract.product_id!r} (must be > 0)"
            )

        for field_name in (
            "price_precision",
            "quantity_precision",
        ):
            precision = getattr(contract, field_name, None)

            if (
                isinstance(precision, bool)
                or not isinstance(precision, int)
                or precision < 0
            ):
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} "
                    f"has invalid {field_name} "
                    f"{precision!r} (must be an int >= 0)"
                )

        for field_name in (
            "tick_size",
            "quantity_step",
            "min_quantity",
        ):
            value = getattr(contract, field_name, None)

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not (value == value)
                or value in (float("inf"), float("-inf"))
            ):
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} "
                    f"has invalid {field_name} "
                    f"{value!r} (must be a finite number)"
                )

            if field_name in ("tick_size", "quantity_step") and value <= 0:
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} "
                    f"has invalid {field_name} "
                    f"{value!r} (must be > 0)"
                )

            if field_name == "min_quantity" and value < 0:
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} "
                    f"has invalid {field_name} "
                    f"{value!r} (must be >= 0)"
                )

        return contract

    @staticmethod
    def _require_execution_evidence(contract, symbol):
        """Refuse writes until product payload semantics have venue evidence."""
        evidence = getattr(contract, "live_execution_evidence", "")
        if not getattr(contract, "live_execution_verified", False) or not isinstance(evidence, str) or not evidence.strip():
            raise InvalidContractError(
                f"contract for symbol {symbol!r} lacks verified live execution evidence"
            )

    # --------------------------------------------------

    def _validated_payload(self, intent, contract):
        """Build then REVALIDATE the venue payload (Phase 14).

        Transport precision must never silently invalidate the
        sizing decision. After building, the size/price are
        re-parsed and must satisfy, or the write is refused via
        InvalidContractError (zero transport):

          * 0 < size <= intent.quantity (+ float dust): the
            venue size is never increased past validation;
          * size >= contract.min_quantity (- dust): the minimum
            survives precision;
          * |price - intent.entry| <= tick_size / 2 (+ dust):
            the price sits on the venue tick grid.
        """
        payload = self.build_payload(intent, contract)

        try:
            size = float(payload["size"])
            price = float(payload["limit_price"])
            quantity = float(intent.quantity)
            entry = float(intent.entry)
            tick = float(contract.tick_size)
            minimum = float(contract.min_quantity)
        except (TypeError, ValueError, KeyError) as exc:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} produced "
                f"a non-numeric payload ({exc})"
            ) from exc

        dust = 1e-9 * max(1.0, abs(quantity), abs(entry))

        # Decimal precision is not the same as venue tick alignment. A
        # rounded decimal can still be off-grid (e.g. 100.13 with tick 0.25).
        # Refuse rather than submit a price the venue will reject.
        try:
            tick_decimal = Decimal(str(contract.tick_size))
            limit_decimal = Decimal(str(payload["limit_price"]))
            if (not tick_decimal.is_finite() or tick_decimal <= 0
                    or not limit_decimal.is_finite() or limit_decimal <= 0
                    or limit_decimal % tick_decimal != 0):
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} produced a "
                    f"limit price not aligned to tick_size {contract.tick_size!r}"
                )
            for field_name in (
                "bracket_take_profit_price",
                "bracket_take_profit_limit_price",
                "bracket_stop_loss_price",
                "bracket_stop_loss_limit_price",
            ):
                if field_name not in payload:
                    continue
                bracket_decimal = Decimal(str(payload[field_name]))
                if (not bracket_decimal.is_finite() or bracket_decimal <= 0
                        or bracket_decimal % tick_decimal != 0):
                    raise InvalidContractError(
                        f"contract for symbol {intent.symbol!r} produced "
                        f"{field_name} not aligned to tick_size {contract.tick_size!r}"
                    )
        except (InvalidOperation, TypeError, ValueError) as exc:
            if isinstance(exc, InvalidContractError):
                raise
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} produced an invalid tick price"
            ) from exc

        tp_key = "bracket_take_profit_price"
        sl_key = "bracket_stop_loss_price"
        has_tp = tp_key in payload
        has_sl = sl_key in payload
        if has_tp != has_sl:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} has an incomplete protective bracket"
            )
        if has_tp and has_sl:
            take_profit_decimal = Decimal(str(payload[tp_key]))
            stop_loss_decimal = Decimal(str(payload[sl_key]))
            side = str(payload.get("side", "")).lower()
            if side == "buy":
                valid_bracket = stop_loss_decimal < limit_decimal < take_profit_decimal
            elif side == "sell":
                valid_bracket = take_profit_decimal < limit_decimal < stop_loss_decimal
            else:
                valid_bracket = False
            if not valid_bracket:
                raise InvalidContractError(
                    f"contract for symbol {intent.symbol!r} has bracket prices "
                    "on the wrong side of the entry"
                )

        if not (size > 0) or size > quantity + dust:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} would "
                f"change validated quantity {quantity!r} to "
                f"venue size {size!r}"
            )
        if size < minimum - dust:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} venue size "
                f"{size!r} violates minimum {minimum!r}"
            )
        if abs(price - entry) > tick / 2.0 + dust:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} venue price "
                f"{price!r} is off the tick grid (entry "
                f"{entry!r}, tick {tick!r})"
            )
        return payload

    # -------------------------------------------------

    def build_payload(self, intent, contract):
        """
        OrderIntent -> Delta CreateOrderRequest.

        Core entry: a GTC limit order at `entry`. When
        attach_brackets is set and the intent carries a
        take-profit/stop-loss, Delta's native bracket fields
        attach both exits to the same create call (no separate
        stop/tp orders to manage).

        Phase-14 sizing-equivalence rule: the venue size is
        floored DOWN to quantity_precision (never rounded up:
        rounding up would silently exceed the validated risk).
        A sub-representation epsilon (1e-9 relative) bridges
        float-grid dust only — never a true half-step. Price is
        formatted to venue precision, then execute() requires exact
        tick-grid alignment and refuses off-grid values before any write.
        """

        precision = contract.price_precision
        direction = str(getattr(intent, "direction", "")).strip().upper()
        if direction not in {"BULLISH", "BEARISH"}:
            raise InvalidContractError(
                f"intent for symbol {intent.symbol!r} has invalid direction "
                f"{getattr(intent, 'direction', None)!r}"
            )

        def price(value):
            return f"{round(value, precision):.{precision}f}"

        def floored_size(value, quantity_precision):
            scale = 10.0 ** quantity_precision
            dust = 1e-9 * max(1.0, abs(float(value)) * scale)
            return (
                math.floor(float(value) * scale + dust) / scale
            )

        side = "sell" if direction == "BEARISH" else "buy"

        try:
            payload_product_id = Decimal(str(contract.product_id))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} has invalid product_id"
            ) from exc
        if (not payload_product_id.is_finite()
                or payload_product_id <= 0
                or payload_product_id != payload_product_id.to_integral_value()):
            raise InvalidContractError(
                f"contract for symbol {intent.symbol!r} has non-integer product_id"
            )

        payload = {

            "product_id": int(payload_product_id),

            "order_type": "limit_order",

            "size": floored_size(
                intent.quantity, contract.quantity_precision
            ),

            "side": side,

            "limit_price": price(
                intent.entry
            ),

            "time_in_force": "gtc",

            "reduce_only": False,

            "post_only": False,

            "client_order_id": (
                self.order_id_factory(intent)
            ),
        }

        if (
            self.attach_brackets
            and intent.take_profit > 0
            and intent.stop_loss > 0
        ):

            tp = price(intent.take_profit)

            sl = price(intent.stop_loss)

            payload["bracket_take_profit_price"] = tp

            payload["bracket_take_profit_limit_price"] = tp

            payload["bracket_stop_loss_price"] = sl

            payload["bracket_stop_loss_limit_price"] = sl

        return payload

    # -------------------------------------------------
    # Order / account management pass-throughs
    # -------------------------------------------------

    def cancel(self, order_id, *, safety=None, product_id=None):
        """Cancel a live working order.

        Cancel issues an exchange WRITE (DELETE /v2/orders with a
        JSON body carrying the order id plus product scope) with
        direct financial effect — killing a working entry/bracket
        can leave a position naked — so it requires the SAME Phase
        11A LIVE safety gate as execute(): an armed SafetyDecision,
        enforced BEFORE any transport call. Product scope is
        mandatory (the venue rejects scopeless cancels); a missing
        product_id fails closed. Reads (fetch/balance/positions)
        stay auth-guarded only: they cannot move money, and
        monitoring must keep working in degraded states.
        """

        LiveSafetyGate.require_decision(
            safety,
            component="DeltaOrderExecutor.cancel",
        )

        base_url = getattr(self.exchange.rest, "base_url", None)
        authority = token_for_live_safety(
            safety, base_url=base_url, endpoint="/v2/orders",
            payload={"id": order_id, "product_id": product_id}, method="DELETE"
        )

        return self.exchange.cancel_order(
            order_id, product_id=product_id, authority=authority
        )

    def fetch(self, order_id):

        return self.exchange.get_order(order_id)

    def balance(self):

        return self.exchange.get_balance()

    def positions(self):

        return self.exchange.get_positions()

from config import risk_settings
