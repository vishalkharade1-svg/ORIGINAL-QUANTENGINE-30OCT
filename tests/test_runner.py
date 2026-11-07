"""
====================================================

QuantEngine

Institutional Test Runner

====================================================
"""

import os
import sys
import unittest

# -----------------------------------------------------
# Add project root to Python path
# -----------------------------------------------------

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# -----------------------------------------------------

def run():

    loader = unittest.TestLoader()

    suite = loader.discover(
        start_dir=os.path.dirname(__file__),
        pattern="test_*.py",
    )

    runner = unittest.TextTestRunner(
        verbosity=2,
    )

    return runner.run(suite)


if __name__ == "__main__":

    run()