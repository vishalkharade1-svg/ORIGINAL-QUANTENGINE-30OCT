"""
====================================================

QuantEngine

Execution Port

Phase 6E -- Real-time integration (paper mode only).

The ONE seam between the risk-validated OrderIntent and an
order destination. The live engine consumes this port
verbatim; the ONLY difference between paper and live is
which adapter is injected (built here / a future
LiveDeltaExecutionAdapter):

    --- OrderIntent -----> ExecutionPort -----> destination

                PaperExecutionAdapter (phase 6E)
                Future LiveDeltaExecutionAdapter

execution port protocol:

    execute(intent)  -> result envelope        {success, response, contract}
    fetch(order_id)  -> order status
    cancel(order_id)
    balance()        -> account/equity snapshot
    positions()      -> open position records

PaperExecutionAdapter is the explicit non-live boundary:
execute() records the would-be intent on the audit list
(PAPER_ORDER_CREATED) and reports the paper mode envelope,
while every live-only read/write operation raises
PaperOnlyError. Paper fills and SL/TP exits are performed
by the engine's TradeSimulator -- the adapter never invents
a second execution path.
====================================================
"""


class PaperOnlyError(RuntimeError):

    """Raised when a live-only ExecutionPort operation is
    attempted on the paper adapter (the future live adapter
    must enable live placement only behind explicit opt-in)."""


class ExecutionPort:
    """Documented protocol. Concrete adapters override the
    operations they support; paper raises on the live ones.

    Live adapters MUST safety-gate every exchange WRITE
    (execute AND cancel) behind LiveSafetyGate before any
    transport call; reads (fetch/balance/positions) are
    auth-guarded at the transport."""

    mode = "unknown"

    def execute(self, intent):
        raise NotImplementedError

    def fetch(self, order_id):
        raise NotImplementedError

    def cancel(self, order_id):
        raise NotImplementedError

    def balance(self):
        raise NotImplementedError

    def positions(self):
        raise NotImplementedError


class PaperExecutionAdapter(ExecutionPort):
    """Eligible-instrument paper routing boundary.

    `execute()` never touches an exchange: it records the
    OrderIntent on `executed` (the PAPER_ORDER_CREATED audit
    trail) and returns the paper-mode success envelope the
    engine recognises. Live-only operations raise
    PaperOnlyError so a mis-wired paper port can never be
    promoted into a live placement by accident.
    """

    mode = "paper"

    def __init__(self):

        self.executed = []

    def execute(self, intent):

        self.executed.append(intent)

        return {
            "success": True,
            "response": {
                "mode": "paper",
                "order_id": getattr(intent, "order_id", None),
            },
            "contract": None,
        }

    def fetch(self, order_id):

        raise PaperOnlyError(
            "PaperExecutionAdapter has no exchange order to fetch."
        )

    def cancel(self, order_id):

        raise PaperOnlyError(
            "PaperExecutionAdapter has no exchange order to cancel."
        )

    def balance(self):

        raise PaperOnlyError(
            "PaperExecutionAdapter has no exchange balance; the "
            "local Account is the paper authority."
        )

    def positions(self):

        raise PaperOnlyError(
            "PaperExecutionAdapter has no exchange positions; "
            "the TradeSimulator is the paper position authority."
        )