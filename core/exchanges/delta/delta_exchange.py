"""
====================================================

Delta Exchange Adapter

Full Delta v2 adapter: public market data plus the
privated authenticated endpoints (wallet balances,
positions, order management) signed per Delta's HMAC-SHA256
scheme (see core/exchanges/delta/delta_auth.py).

This replaces the historical NotImplementedError stub -- the
Delta Order Executor requires every BaseExchange method to be
real.

====================================================
"""

from core.exchanges.base_exchange import BaseExchange

from core.exchanges.delta.delta_auth import DeltaSignedREST
from core.exchanges.delta.delta_products import DeltaProducts
from core.exchanges.delta.write_authority import (
    ALL_KINDS,
    OFFLINE_FALLBACK_BASE_URL,
    require_write_authority,
)


class DeltaExchange(BaseExchange):

    def __init__(
        self,
        api_key=None,
        api_secret=None,
        rest=None,
        base_url=None,
    ):

        from config.settings import settings

        self.api_key = (
            api_key
            if api_key is not None
            else settings.API_KEY
        )

        self.api_secret = (
            api_secret
            if api_secret is not None
            else settings.API_SECRET
        )

        self.rest = (
            rest
            if rest is not None
            else DeltaSignedREST(
                api_key=self.api_key,
                api_secret=self.api_secret,
                base_url=base_url,
            )
        )

    # -------------------------------------------------

    @property
    def authenticated(self):
        # Authentication state is a security boundary. Do not let a
        # truthy string such as "false" authorize private endpoints.
        rest_state = getattr(self.rest, "authenticated", None)
        if rest_state is not None:
            return rest_state is True
        return bool(
            str(self.api_key or "").strip()
            and str(self.api_secret or "").strip()
        )

    # -------------------------------------------------

    def _require_auth(self):

        if not self.authenticated:

            raise RuntimeError(
                "Delta private endpoint requires "
                "DELTA_API_KEY and DELTA_API_SECRET "
                "(config/.env)"
            )

    # -------------------------------------------------
    # Public market data
    # -------------------------------------------------

    def get_products(self):

        return DeltaProducts().download()

    # -------------------------------------------------
    # Account
    # -------------------------------------------------

    def get_balance(self):

        self._require_auth()

        return self.rest.get(
            "/v2/wallet/balances"
        )

    def get_positions(self):

        self._require_auth()

        return self.rest.get(
            "/v2/positions"
        )

    # -------------------------------------------------
    # Orders
    # -------------------------------------------------

    def place_order(self, order, *, authority=None):

        # Phase193B: the adapter write path is authorization-gated HERE, not
        # only in higher-level executors.  A direct DeltaExchange call with
        # no armed token is refused before any transport write.
        base_url = getattr(self.rest, "base_url", None) or OFFLINE_FALLBACK_BASE_URL
        require_write_authority(
            authority, base_url=base_url, endpoint="/v2/orders",
            kinds=ALL_KINDS, payload=order, method="POST",
        )

        self._require_auth()

        rest_post = getattr(self.rest, "post", None)

        # Phase193B: transports that enforce write authority themselves
        # (production DeltaSignedREST) receive the token here, so the
        # REST boundary independently verifies mint + binding (defense
        # in depth).  Offline test doubles without the attribute keep
        # the legacy call signature; the adapter gate above already
        # validated the token.
        if bool(getattr(self.rest, "enforce_write_authority", False)):
            return rest_post(
                "/v2/orders",
                payload=order,
                authority=authority,
            )

        return rest_post(
            "/v2/orders",
            payload=order,
        )

    def cancel_order(self, order_id, product_id=None, *, authority=None):

        self._require_auth()
        if product_id is None:
            raise ValueError(
                "cancel_order requires product_id for venue scoping"
            )
        base_url = getattr(self.rest, "base_url", None) or OFFLINE_FALLBACK_BASE_URL
        require_write_authority(
            authority, base_url=base_url, endpoint="/v2/orders",
            kinds=ALL_KINDS,
            payload={"id": order_id, "product_id": product_id}, method="DELETE",
        )

        # Venue-verified shape (Testnet, 2026-10-11): DELETE /v2/orders
        # with a JSON body carrying the order id plus product scope.
        # The legacy DELETE /v2/orders/{id} route does not exist on
        # the venue (404); product scope is mandatory (bare scope is
        # bad_schema), so a missing product_id fails closed here
        # instead of emitting a guaranteed-rejected request.
        # Phase193B: pass the token down to enforcing transports, like
        # place_order (adapter already validated mint + binding).
        if bool(getattr(self.rest, "enforce_write_authority", False)):
            return self.rest.delete(
                "/v2/orders",
                payload={"id": order_id, "product_id": product_id},
                authority=authority,
            )

        return self.rest.delete(
            "/v2/orders",
            payload={"id": order_id, "product_id": product_id},
        )

    def get_order(self, order_id):

        self._require_auth()

        return self.rest.get(
            f"/v2/orders/{order_id}"
        )

    def get_reconciliation_snapshot(self, *, product_id):
        """Fetch read-only order/fill/position evidence for reconciliation.

        The adapter is deliberately separate from order execution. It issues
        authenticated GET requests only and raises if any endpoint is
        unavailable or malformed; it never returns a clean partial snapshot.
        """
        self._require_auth()
        from core.exchanges.delta.reconciliation_read_adapter import (
            DeltaReconciliationReadAdapter,
        )
        return DeltaReconciliationReadAdapter(self.rest).capture(product_id=product_id)

    # -------------------------------------------------
    # Product id lookup (symbol -> Delta product id)
    # -------------------------------------------------

    def get_product_id(
        self,
        symbol,
        products=None,
    ):

        data = (
            products
            if products is not None
            else self.get_products()
        )

        result = (
            data.get("result")
            if isinstance(data, dict)
            else data
        )

        for product in result or []:

            if product.get("symbol") == symbol:
                return product.get("id")

        return None
