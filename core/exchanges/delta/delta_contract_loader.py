"""
====================================================

Delta Contract Loader

Loads the FULL Delta Exchange product universe: every
perpetual future, every listed option (call + put, all
strikes/expiries) and every tokenized/spot instrument
the exchange returns from /v2/products.

The historic perpetual-only filter is gone by default
(that is what capped the backtester at BTCUSD-style
perpetuals). Pass contract_types to restrict to a
whitelist, e.g. ("perpetual_futures",).

====================================================
"""

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_products import DeltaProducts
from core.exchanges.delta.delta_mapper import DeltaMapper


class ContractLoadError(RuntimeError):

    """The Delta product universe could not be loaded:
    transport failure or an unexpected /v2/products
    schema. Raised INSTEAD of a bare KeyError so callers
    see a typed connection/data error with no secrets."""


class DeltaContractLoader:

    def load(self, contract_types=None):
        """
        Build a registry of Delta contracts.

        contract_types=None loads EVERY product Delta lists
        (perpetual futures, call/put options, tokenized
        instruments). Pass an iterable of lowercase contract
        type names to load only those (e.g.
        ("perpetual_futures",) for the old behavior).
        """

        registry = ContractRegistry()

        try:
            downloaded = DeltaProducts().download()
        except ContractLoadError:
            raise
        except Exception as error:
            raise ContractLoadError(
                "Delta products download failed "
                "({}): no universe loaded.".format(
                    type(error).__name__
                )
            ) from error

        try:
            products = downloaded["result"]
        except (KeyError, TypeError) as error:
            raise ContractLoadError(
                "Delta products payload has no 'result' "
                "list: unexpected /v2/products schema."
            ) from error

        if not isinstance(products, list):
            raise ContractLoadError(
                "Delta products payload 'result' is not a "
                "list: unexpected /v2/products schema."
            )

        if not products:
            raise ContractLoadError(
                "Delta products payload 'result' is empty: "
                "no universe loaded (refusing to create an "
                "empty contract registry)."
            )

        mapper = DeltaMapper()

        for index, product in enumerate(products):

            if not isinstance(product, dict):
                raise ContractLoadError(
                    "Delta products payload 'result[{}]' is "
                    "not an object: unexpected /v2/products "
                    "schema.".format(index)
                )

            contract_type = product.get(
                "contract_type",
                "",
            )

            if not isinstance(contract_type, str):
                raise ContractLoadError(
                    "Delta products payload 'result[{}]' has "
                    "a non-string contract_type: unexpected "
                    "/v2/products schema.".format(index)
                )

            contract_type = contract_type.lower()

            if (
                contract_types is not None
                and contract_type not in set(contract_types)
            ):
                continue

            try:
                mapped = mapper.map(product)
            except ContractLoadError:
                raise
            except Exception as error:
                raise ContractLoadError(
                    "Delta products payload 'result[{}]' "
                    "could not be mapped ({}): unexpected "
                    "/v2/products schema.".format(
                        index, type(error).__name__
                    )
                ) from error

            if not getattr(mapped, "symbol", ""):
                raise ContractLoadError(
                    "Delta products payload 'result[{}]' "
                    "mapped to an empty symbol: unexpected "
                    "/v2/products schema.".format(index)
                )

            registry.add(mapped)

        return registry