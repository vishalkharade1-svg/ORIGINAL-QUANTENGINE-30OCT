"""
====================================================

Multi-Symbol Scanning

Phase 6C: orchestrate one isolated pipeline per
instrument in the ELIGIBLE universe, aggregate the
per-symbol outcomes, and return a deterministically
ordered canonical result.

    MultiSymbolScanner.scan(universe)
        -> MultiSymbolScanResult

====================================================
"""

from core.scanning.scan_result import MultiSymbolScanResult
from core.scanning.scan_result import ScanStatus
from core.scanning.scan_result import SymbolScanResult
from core.scanning.multi_symbol_scanner import MultiSymbolScanner
from core.scanning.symbol_pipeline import SymbolPipeline

__all__ = [
    "MultiSymbolScanResult",
    "MultiSymbolScanner",
    "ScanStatus",
    "SymbolPipeline",
    "SymbolScanResult",
]