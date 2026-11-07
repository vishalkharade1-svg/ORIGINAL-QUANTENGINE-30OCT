"""
====================================================

QuantEngine

Logging Configuration

Stdlib logging, deliberately dependency-free (see note
below on core/logger.py). Library modules should call
get_logger(__name__) and log at DEBUG/INFO -- they must
never print() directly, since that can't be silenced in
production and pollutes test output.

By default, nothing is printed: get_logger() attaches a
NullHandler until configure_logging() is called explicitly
(e.g. from main.py, a backtest script, or a test that wants
verbose output).

Note: core/logger.py predates this module and configures a
loguru-based logger, but loguru is not an installed
dependency and nothing in the codebase currently imports
core/logger.py. Rather than silently depending on a package
that may not be installed, this module uses only the
standard library. If loguru is intentionally added as a
dependency later, core/logger.py and this module should be
reconciled into one logging setup.

====================================================
"""

import logging

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:

    logger = logging.getLogger(name)

    if not logger.handlers and not _CONFIGURED:

        logger.addHandler(logging.NullHandler())

    return logger


def configure_logging(level=logging.INFO, fmt=None):
    """
    Call once, from an entrypoint (main.py, a backtest
    script, a test), to actually see log output. Without
    calling this, all QuantEngine loggers are silent.
    """

    global _CONFIGURED

    logging.basicConfig(
        level=level,
        format=fmt or "%(levelname)-8s %(name)-40s %(message)s",
    )

    _CONFIGURED = True
