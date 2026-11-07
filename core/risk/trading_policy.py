"""Runtime trading risk/exit policy authority.

The policy is intentionally separate from frozen research thresholds.  It is
operator-configurable through the authenticated control UI/API and resolves
by exact instrument key, falling back to the global default.

No timestamps, UUIDs, randomness, or secrets are stored.  Persisted JSON is
canonicalized with sorted keys and explicit LF line endings, so identical
policy state produces identical bytes on every platform.  (A text-mode write
used to translate "\n" to CRLF on Windows; that re-drifted the persisted file
away from its recorded Phase131 byte pin on every Windows-side save, which the
Phase158 post-audit repair restored.)
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
import tempfile
from threading import RLock


DEFAULT_MIN_RR = 1.0
DEFAULT_MAX_RR = 20.0
DEFAULT_TRAILING_ENABLED = True
DEFAULT_TRAILING_ACTIVATION_R = 1.0
DEFAULT_TRAILING_DISTANCE_R = 0.5
DEFAULT_TRAILING_METHOD = "R_DISTANCE"
DEFAULT_TRAILING_STEP_R = 0.0
DEFAULT_AUTO_EXIT_ON_OPPOSITE_SIGNAL = True

SUPPORTED_TRAILING_METHODS = ("R_DISTANCE",)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The persisted operator policy lives at a repo-anchored path, never a
# CWD-relative one: the trading policy is a safety authority, and a
# process started from another working directory must load the SAME
# operator policy (or compiled defaults when absent) -- never a
# stranger file that happens to share the relative path, and never an
# accidental fresh default that silently drops overrides.
_POLICY_PATH = _REPO_ROOT / "data" / "runtime" / "risk_policy_overrides.json"


@dataclass(frozen=True, slots=True)
class TradingPolicy:
    min_rr: float = DEFAULT_MIN_RR
    max_rr: float = DEFAULT_MAX_RR
    trailing_enabled: bool = DEFAULT_TRAILING_ENABLED
    trailing_activation_r: float = DEFAULT_TRAILING_ACTIVATION_R
    trailing_distance_r: float = DEFAULT_TRAILING_DISTANCE_R
    trailing_method: str = DEFAULT_TRAILING_METHOD
    trailing_step_r: float = DEFAULT_TRAILING_STEP_R
    auto_exit_on_opposite_signal: bool = DEFAULT_AUTO_EXIT_ON_OPPOSITE_SIGNAL

    def validate(self) -> "TradingPolicy":
        import math

        vals = (self.min_rr, self.max_rr, self.trailing_activation_r,
                self.trailing_distance_r, self.trailing_step_r)
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError("trading policy values must be finite")
        if float(self.min_rr) < 1.0:
            raise ValueError("minimum R:R cannot be below 1:1")
        if float(self.max_rr) > 20.0:
            raise ValueError("maximum R:R cannot exceed 1:20")
        if float(self.min_rr) > float(self.max_rr):
            raise ValueError("minimum R:R cannot exceed maximum R:R")
        if float(self.trailing_activation_r) <= 0.0:
            raise ValueError("trailing activation R must be positive")
        if float(self.trailing_distance_r) <= 0.0:
            raise ValueError("trailing distance R must be positive")
        method = str(self.trailing_method or "").strip().upper()
        if method not in SUPPORTED_TRAILING_METHODS:
            raise ValueError(
                "unsupported trailing method %r (supported: %s)"
                % (self.trailing_method, ", ".join(SUPPORTED_TRAILING_METHODS))
            )
        if float(self.trailing_step_r) < 0.0:
            raise ValueError("trailing step R cannot be negative")
        if not isinstance(self.trailing_enabled, bool):
            raise ValueError("trailing_enabled must be boolean")
        if not isinstance(self.auto_exit_on_opposite_signal, bool):
            raise ValueError("auto_exit_on_opposite_signal must be boolean")
        return self


class TradingPolicyManager:
    """Thread-safe global + exact-instrument policy registry."""

    def __init__(self, path: Path | str = _POLICY_PATH):
        self.path = Path(path)
        self._lock = RLock()
        self._global = TradingPolicy().validate()
        self._overrides: dict[str, TradingPolicy] = {}
        # Preserve the operator-facing spelling for API snapshots while using
        # canonical keys internally for lookup. Formatting variants resolve to
        # the same policy but the API does not silently rewrite the symbol the
        # operator submitted.
        self._display_keys: dict[str, str] = {}
        self._load()

    @staticmethod
    def _key(symbol: str | None) -> str:
        """Normalize formatting variants without conflating instruments.

        Separators commonly used in the same venue symbol (BTC-USD,
        BTC/USD, BTC_USD, BTCUSD) are formatting, not identity. Quote
        assets and venue prefixes remain significant: ETHUSD is NOT
        silently aliased to ETHUSDT, and DELTA:BTCUSD remains distinct.
        """
        raw = str(symbol or "").strip().upper()
        return re.sub(r"[\s/_-]+", "", raw)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._global = TradingPolicy(**dict(raw.get("global", {}))).validate()
            overrides = raw.get("instruments", {})
            loaded: dict[str, TradingPolicy] = {}
            display_keys: dict[str, str] = {}
            for display_key, values in sorted(overrides.items()):
                key = self._key(display_key)
                if not key:
                    continue
                if key in loaded:
                    raise ValueError(
                        "duplicate instrument policy keys after normalization: "
                        f"{display_keys[key]!r} and {display_key!r}"
                    )
                loaded[key] = TradingPolicy(**dict(values)).validate()
                display_keys[key] = str(display_key)
            self._overrides = loaded
            self._display_keys = display_keys
        except Exception as exc:
            raise ValueError("invalid persisted trading policy: %s" % exc) from exc

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "global": asdict(self._global),
            "instruments": {
                self._display_keys.get(key, key): asdict(self._overrides[key])
                for key in sorted(self._overrides)
            },
        }
        data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        fd, name = tempfile.mkstemp(prefix="risk_policy.", suffix=".tmp", dir=str(self.path.parent))
        try:
            # newline="\n" is deliberate: with text-mode translation a save on
            # Windows rewrites the file with CRLF and drifts it away from its
            # recorded Phase131 pin (LF).  Persistence must be byte-identical
            # on every platform for the same policy state.
            with open(fd, "w", encoding="utf-8", newline="\n", closefd=True) as fh:
                fh.write(data)
                fh.flush()
            Path(name).replace(self.path)
        finally:
            try:
                Path(name).unlink()
            except FileNotFoundError:
                pass

    def get(self, symbol: str | None = None) -> TradingPolicy:
        with self._lock:
            return self._overrides.get(self._key(symbol), self._global)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "global": asdict(self._global),
                "instruments": {
                    self._display_keys.get(key, key): asdict(self._overrides[key])
                    for key in sorted(self._overrides)
                },
                "bounds": {
                    "min_rr": [1.0, 20.0],
                    "max_rr": [1.0, 20.0],
                    "trailing_methods": list(SUPPORTED_TRAILING_METHODS),
                    "trailing_step_r": [0.0, None],
                },
                "production_ready": False,
            }

    def set_global(self, values: dict) -> TradingPolicy:
        policy = TradingPolicy(**values).validate()
        with self._lock:
            self._global = policy
            self._persist()
            return policy

    def set_instrument(self, symbol: str, values: dict) -> TradingPolicy:
        key = self._key(symbol)
        if not key:
            raise ValueError("instrument/symbol is required")
        policy = TradingPolicy(**values).validate()
        display_key = str(symbol).strip().upper()
        with self._lock:
            # Keep a stable existing display spelling when a formatting alias
            # updates an already-configured canonical instrument.
            self._overrides[key] = policy
            self._display_keys.setdefault(key, display_key)
            self._persist()
            return policy

    def reset_instrument(self, symbol: str) -> None:
        key = self._key(symbol)
        with self._lock:
            self._overrides.pop(key, None)
            self._display_keys.pop(key, None)
            self._persist()


_manager = TradingPolicyManager()


def trading_policy(symbol: str | None = None) -> TradingPolicy:
    return _manager.get(symbol)


def trading_policy_manager() -> TradingPolicyManager:
    return _manager


@contextmanager
def policy_override(policy: TradingPolicy, symbol: str | None = None):
    """Temporarily apply a validated policy for deterministic evaluation.

    Global-override mode restores the exact previous object; instrument mode
    removes the override again when none existed before.  The manager lock is
    held only while swapping, never across caller execution.
    """
    manager = _manager
    validated = policy.validate()
    key = manager._key(symbol) if symbol is not None else None
    with manager._lock:
        if key is None:
            previous = manager._global
            manager._global = validated
        else:
            if not key:
                raise ValueError("instrument/symbol is required")
            previous = manager._overrides.get(key)
            previous_display = manager._display_keys.get(key)
            manager._overrides[key] = validated
            manager._display_keys.setdefault(key, str(symbol).strip().upper())
    try:
        yield validated
    finally:
        with manager._lock:
            if key is None:
                manager._global = previous
            elif previous is None:
                manager._overrides.pop(key, None)
                manager._display_keys.pop(key, None)
            else:
                manager._overrides[key] = previous
                if previous_display is not None:
                    manager._display_keys[key] = previous_display
