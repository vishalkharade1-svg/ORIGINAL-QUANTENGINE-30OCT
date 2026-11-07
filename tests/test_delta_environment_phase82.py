import pytest
from research.economics.delta_environment import INDIA_TESTNET, INDIA_PRODUCTION, resolve_environment, validate_endpoints


def test_india_testnet_mapping_is_explicit():
    env = resolve_environment("india_testnet")
    assert env == INDIA_TESTNET
    assert env.rest_base_url == "https://cdn-ind.testnet.deltaex.org"
    assert env.private_ws_url == "wss://socket-ind.testnet.deltaex.org"


def test_production_mapping_is_explicit():
    env = resolve_environment("india_production")
    assert env == INDIA_PRODUCTION


def test_unknown_environment_rejected():
    with pytest.raises(ValueError):
        resolve_environment("india_staging")


def test_testnet_production_endpoint_mix_rejected():
    with pytest.raises(ValueError, match="endpoint/environment mismatch"):
        validate_endpoints(
            "india_testnet",
            rest_base_url=INDIA_PRODUCTION.rest_base_url,
            private_ws_url=INDIA_PRODUCTION.private_ws_url,
        )
