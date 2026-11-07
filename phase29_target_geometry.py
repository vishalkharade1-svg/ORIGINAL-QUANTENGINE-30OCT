"""
Phase 29 - Target Geometry Diagnosis

Inspect the strategy's target-generation logic and calculate the distribution
of candidate planned RR before and after all applicable filters.

The goal is to identify why so many candidates have targets above 20R and
distinguish between:
- Strategy-design characteristics
- Incorrect stop or target geometry
- Incorrect RR arithmetic
- Entry-price and execution-price differences
- Tick-size and contract constraints
- Risk-policy integration defects
- Invalid or stale market structure
"""

import json
import sys
import math
from pathlib import Path

sys.path.insert(0, r'F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE')

from core.setup.setup_candidate import SetupCandidate
from core.risk.order_intent import OrderIntent
from core.risk.risk_engine import risk_reward_allowed
from core.backtesting.accounting import risk_reward_allowed as accounting_rr


def safe_float(val, default=0.0):
    """Safely convert to float, returning default on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def calculate_rr(entry, stop, target):
    """Calculate planned reward-to-risk ratio.
    
    RR = |target - entry| / |stop - entry|
    For long: stop < entry < target
    For short: stop > entry > target
    """
    entry = safe_float(entry)
    stop = safe_float(stop)
    target = safe_float(target)
    
    if entry == 0 or stop == 0 or target == 0:
        return None
    
    abs_stop_dist = abs(entry - stop)
    abs_target_dist = abs(target - entry)
    
    if abs_stop_dist == 0:
        return None
    
    rr = abs_target_dist / abs_stop_dist
    return round(rr, 6)


def is_valid_long(entry, stop, target):
    """Validate long position geometry: stop < entry < target."""
    return stop < entry < target


def is_valid_short(entry, stop, target):
    """Validate short position geometry: stop > entry > target."""
    return stop > entry > target


def main():
    # Load datasets
    with open('data/history/BTCUSDT_1m_phase17_fresh.json', 'r') as f:
        certified = json.load(f)
    with open('data/history/BTCUSDT_1m_oos_topup.json', 'r') as f:
        extended = json.load(f)
    
    raw_certified = certified['raw']
    raw_extended = extended['raw']
    
    print('=== Phase 29: Target Geometry Diagnosis ===')
    print()
    
    # Analyze a sample of candidates from each dataset
    sample_size = 200
    
    print('=== Certified Dataset Sample Analysis (first {} candidates) ===' .format(sample_size))
    print()
    
    rr_bullish = []  # long positions
    rr_bearish = []  # short positions
    rr_bullish_above_20 = 0
    rr_bearish_above_20 = 0
    rr_bullish_below_1 = 0
    rr_bearish_below_1 = 0
    valid_geometry = 0
    invalid_geometry = 0
    
    for i, row in enumerate(raw_certified[:sample_size]):
        # Create a minimal setup candidate
        # We need entry, stop, target from the row data
        # The actual structure varies; let's examine what's available
        pass
    
    # Instead, let's examine the actual structure of the data
    print('Examining data structure...')
    if len(raw_certified) > 0:
        sample = raw_certified[0]
        print(f'Sample row keys: {list(sample.keys())}')
        for k, v in sample.items():
            if isinstance(v, (int, float)):
                print(f'  {k}: {v} ({type(v).__name__})')
            else:
                print(f'  {k}: {str(v)[:50]}')
    
    print()
    print('=== Extended Dataset Sample ===')
    if len(raw_extended) > 0:
        sample = raw_extended[0]
        print(f'Sample row keys: {list(sample.keys())}')
        for k, v in sample.items():
            if isinstance(v, (int, float)):
                print(f'  {k}: {v} ({type(v).__name__})')
            else:
                print(f'  {k}: {str(v)[:50]}')
    
    print()
    print('=== RR Distribution Analysis (requires full strategy logic) ===')
    print('The RR calculation depends on the strategy\'s target-generation logic.')
    print('Without access to the full strategy code, we can only examine')
    print('the raw data structure and manually calculated RRs.')


if __name__ == '__main__':
    main()