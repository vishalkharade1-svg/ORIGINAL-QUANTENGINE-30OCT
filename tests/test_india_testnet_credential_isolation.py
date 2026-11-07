"""India Testnet scripts must never reinterpret generic production credentials."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, module_name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_order_experiment_refuses_generic_credentials(monkeypatch):
    monkeypatch.setenv("DELTA_API_KEY", "production-key-placeholder")
    monkeypatch.setenv("DELTA_API_SECRET", "production-secret-placeholder")
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_SECRET", raising=False)
    mod = load_script("bounded_testnet_order_experiment.py", "bounded_testnet_order_test")
    assert mod.main(["--execute"]) == 2


def test_reconciled_experiment_refuses_generic_credentials(monkeypatch):
    monkeypatch.setenv("DELTA_API_KEY", "production-key-placeholder")
    monkeypatch.setenv("DELTA_API_SECRET", "production-secret-placeholder")
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_INDIA_TESTNET_API_SECRET", raising=False)
    mod = load_script("bounded_testnet_reconciled_experiment.py", "bounded_testnet_reconciled_test")
    assert mod.main(["--execute"]) == 2
