"""
====================================================

QuantEngine

Instrument Registry (persistent)

Phase 6 -- Universal Instrument Discovery.

The single source of truth for every instrument the
engine has discovered. Two responsibilities:

1. PERSISTENT CATALOG -- a JSON file survives engine
   restarts, so a newly listed product is detected by
   comparing the next discovery pass against what we
   ALREADY know (not an empty slice of history).

2. LIFECYCLE -- every instrument carries one of:
   NEWLY_LISTED / ACTIVE / ELIGIBLE / INELIGIBLE /
   DELISTED. Only ELIGIBLE may reach execution (the
   never-trade-everything rule); the others are
   collected / monitored / filtered.

The registry NEVER talks to an exchange. Discovery
hands it normalized Instruments and it decides state.
====================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional

from core.registry.instrument import Instrument
from core.registry.product_types import (
    EXECUTABLE_STATES,
    PRODUCT_STATE_ACTIVE,
    PRODUCT_STATE_DELISTED,
    PRODUCT_STATE_ELIGIBLE,
    PRODUCT_STATE_INELIGIBLE,
    PRODUCT_STATE_NEWLY_LISTED,
)

_HEARTBEAT_KEYS = (
    "symbol",
    "product_type",
    "underlying_asset",
    "quote_asset",
    "tick_size",
    "quantity_step",
    "minimum_quantity",
    "trading_enabled",
)


class InstrumentRegistry:

    def __init__(self, path=None):
        self._instruments: Dict[str, Instrument] = {}
        self.path = Path(path) if path is not None else None
        self.newly_listed_seen = {}  # key -> first-seen catalog
        # Confirmed keys from the PREVIOUS discovery pass -- a
        # NEWLY_LISTED instrument only becomes ACTIVE after it
        # survives onto a LATER pass (one consistent resighting).
        self._previous_sightings = set()
        if self.path is not None and self.path.exists():
            self.load()

    # =====================================================
    # Collection
    # =====================================================

    def get(self, key):
        return self._instruments.get(key)

    def get_by_symbol(self, symbol, exchange="DELTA"):
        return self.get(Instrument.key_for(exchange, symbol))

    def all(self) -> List[Instrument]:
        return list(self._instruments.values())

    def __len__(self):
        return len(self._instruments)

    # =====================================================
    # Upsert / refresh (the discovery heartbeat)
    # =====================================================

    def _store(self, instrument: Instrument):
        # NOT schemeless: an instrument with no tick/quantity step
        # can never fill a real order size -- keep the record, but
        # the mandatory marker is the contract precision rule.
        existing = self._instruments.get(instrument.key)
        if existing is None:
            self._instruments[instrument.key] = instrument
            self.newly_listed_seen[instrument.key] = instrument.to_dict()
            return instrument, True
        # Preserve the lifecycle state carried by the persistent
        # record -- a repeat sighting must never silently wipe
        # ELIGIBLE / INELIGIBLE / DELISTED on the stored object.
        instrument.state = existing.state
        self._instruments[instrument.key] = instrument
        return instrument, False

    def upsert(self, instrument: Instrument):
        """Register product instruments after normalization. The
        FIRST sighting is NEWLY_LISTED (candidate); a repeated
        sighting with changed economics goes back to NEWLY_LISTED
        (re-validated); a DELISTED instrument that reappears is
        re-listed and candidate again; an unchanged NEWLY_LISTED
        instrument becomes ACTIVE once it is sighted again."""
        stored, first = self._store(instrument)
        if first:
            stored.state = PRODUCT_STATE_NEWLY_LISTED
        elif self._economics_changed(stored):
            stored.state = PRODUCT_STATE_NEWLY_LISTED
            self.newly_listed_seen[stored.key] = stored.to_dict()
        elif stored.state == PRODUCT_STATE_DELISTED:
            stored.state = PRODUCT_STATE_NEWLY_LISTED
            self.newly_listed_seen[stored.key] = stored.to_dict()
        elif stored.state in (PRODUCT_STATE_NEWLY_LISTED,):
            stored.state = PRODUCT_STATE_ACTIVE
        return stored, first

    def _economics_changed(self, instrument: Instrument):
        prior = self.newly_listed_seen.get(instrument.key)
        if prior is None:
            return False
        return any(
            prior.get(k) != getattr(instrument, k, "")
            for k in _HEARTBEAT_KEYS
        )

    def mark_present(self, seen_keys: Iterable[str]):
        """Discovery heartbeat, run per refresh:
          - a NEWLY_LISTED instrument that was already sighted on a
            PREVIOUS pass is confirmed -> ACTIVE (a brand-new first
            sighting stays a candidate for a later resolution);
          - every known instrument that no longer appears in the
            exchange product list is DELISTED (gracefully, never
            deleted -- history stays loadable)."""
        seen = set(seen_keys)
        for key, instrument in list(self._instruments.items()):
            if key not in seen and instrument.state != PRODUCT_STATE_DELISTED:
                instrument.state = PRODUCT_STATE_DELISTED
            elif (
                key in seen
                and instrument.state == PRODUCT_STATE_NEWLY_LISTED
                and key in self._previous_sightings
            ):
                instrument.state = PRODUCT_STATE_ACTIVE
        self._previous_sightings = seen

    # =====================================================
    # Eligibility transitions
    # =====================================================

    def mark_eligible(self, key):
        inst = self.get(key)
        if inst is not None:
            inst.state = PRODUCT_STATE_ELIGIBLE
            inst.metadata.pop("eligibility_reason", None)
        return inst

    def mark_ineligible(self, key, reason="unspecified"):
        inst = self.get(key)
        if inst is not None:
            inst.state = PRODUCT_STATE_INELIGIBLE
            inst.metadata["eligibility_reason"] = reason
        return inst

    # =====================================================
    # Queries
    # =====================================================

    def by_state(self, state):
        return [
            i for i in self._instruments.values()
            if i.state == state
        ]

    def executable(self):
        return [
            i for i in self._instruments.values()
            if i.state in EXECUTABLE_STATES
        ]

    def newly_listed(self):
        return self.by_state(PRODUCT_STATE_NEWLY_LISTED)

    def delisted(self):
        return self.by_state(PRODUCT_STATE_DELISTED)

    def discoverable(self):
        return [
            i for i in self._instruments.values()
            if i.state not in (PRODUCT_STATE_DELISTED,)
        ]

    # =====================================================
    # Persistence
    # =====================================================

    def to_dict(self):
        return {
            key: {"state": i.state, "instrument": i.to_dict()}
            for key, i in self._instruments.items()
        }

    def load(self):
        import json
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        self._instruments.clear()
        self.newly_listed_seen.clear()
        for key, entry in raw.items():
            data = entry.get("instrument", entry)
            inst = Instrument.from_dict(data)
            inst.state = entry.get("state", inst.state)
            self._instruments[key] = inst
            if inst.state == PRODUCT_STATE_NEWLY_LISTED:
                self.newly_listed_seen[key] = data
        return self

    def save(self, path=None):
        import json
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("InstrumentRegistry has no path to save to")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        return target