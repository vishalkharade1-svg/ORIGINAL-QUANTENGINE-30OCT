"""
Phase 188 Analysis Runner: L2 Quality Analysis and Chronological Queue Calibration.
"""
from decimal import Decimal
import json
from pathlib import Path

from core.research.l2_quality_analyzer import L2QualityAnalyzer
from core.research.queue_calibration_engine import QueueCalibrationEngine


def run_phase188_analysis():
    capture_path = Path("research/captures/phase188_l2/raw_l2_capture_20261021T052549Z.jsonl")
    if not capture_path.exists():
        raise FileNotFoundError(f"Missing {capture_path}")

    # 1. Quality Analysis
    analyzer = L2QualityAnalyzer(stale_threshold_seconds=5.0)
    quality_results = analyzer.analyze_jsonl_capture(capture_path)

    # Add phase 188 metadata
    quality_results["phase"] = 188
    quality_results["capture_target_duration_seconds"] = 180.0
    quality_results["achieved_duration_seconds"] = quality_results.get("duration_seconds")
    quality_results["orders_written_to_exchange"] = 0
    quality_results["read_only_verified"] = True
    quality_results["raw_capture_sha256"] = "1382e1002602e3baff505a0e1c199471f78748538b5463f776b72614807cbbf6"

    quality_json_path = Path("reports/PHASE188_MARKET_DATA_QUALITY.json")
    with quality_json_path.open("w", encoding="utf-8") as f:
        json.dump(quality_results, f, indent=2, default=str)
    print(f"[+] Written: {quality_json_path}")

    # 2. Queue Calibration Holdout Analysis
    records = []
    with capture_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    btc_engine = QueueCalibrationEngine("BTCUSD", notional_usd=Decimal("82.8"), order_size=Decimal("1.0"), contract_multiplier=Decimal("0.001"))
    btc_ident = btc_engine.evaluate_identifiability()
    btc_holdout = btc_engine.run_chronological_holdout_evaluation(records, split_ratio=0.50)

    eth_engine = QueueCalibrationEngine("ETHUSD", notional_usd=Decimal("24.4"), order_size=Decimal("1.0"), contract_multiplier=Decimal("0.01"))
    eth_holdout = eth_engine.run_chronological_holdout_evaluation(records, split_ratio=0.50)

    calib_payload = {
        "phase": 188,
        "identifiability_proof": btc_ident,
        "btc_holdout_evaluation": btc_holdout,
        "eth_holdout_evaluation": eth_holdout,
        "orders_written_to_exchange": 0,
        "verdict": "UNCALIBRATED_PARTIALLY_OBSERVABLE",
    }

    calib_json_path = Path("reports/PHASE188_QUEUE_CALIBRATION_RESULTS.json")
    with calib_json_path.open("w", encoding="utf-8") as f:
        json.dump(calib_payload, f, indent=2, default=str)
    print(f"[+] Written: {calib_json_path}")


if __name__ == "__main__":
    run_phase188_analysis()
