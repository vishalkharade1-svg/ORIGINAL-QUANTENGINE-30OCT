"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- ladder

Conservative, deterministic mapping from the frozen 9M evidence ladder
(final_status) plus the conditional (regime-scoped) flag to a 9N review
recommendation.

The 9N ladder is deliberately CONSERVATIVE:

   * a 7E NO-GO finding is always 7E_BLOCKED -- the frozen directional
     safety boundary can never be softened by OOS evidence;
   * a regime-scoped (conditional) claim is NEVER promoted into a
     universal PROMISING / ROBUST_RESEARCH_FINDING tier -- because its
     universality is not established, the top unconditional tiers are
     reserved for genuinely unconditional findings (robustness LOW
     blocks the top tier for any claim).

Mapping (deterministic, total over the 9M ladder):

   9M BLOCKED                   -> 7E_BLOCKED
   9M UNAVAILABLE               -> NO_EVIDENCE
   9M INCONCLUSIVE              -> INCONCLUSIVE
   9M REJECTED                  -> REJECTED
   9M OOS_PARTIAL               -> REQUIRES_MORE_OOS
   9M OOS_PROMISING, cond=True  -> CONDITIONAL
   9M OOS_PROMISING, cond=False -> PROMISING
   9M OOS_ROBUST,    cond=True  -> CONDITIONAL
   9M OOS_ROBUST,    cond=False -> PROMISING
   9M VALIDATED_RESEARCH_ONLY, cond=True  -> CONDITIONAL
   9M VALIDATED_RESEARCH_ONLY, cond=False -> ROBUST_RESEARCH_FINDING
====================================================================
"""

from core.research.oos import constants as _oos
from core.research.recommendation import constants as _c


def recommend_status(oos_status, is_conditional=False, seven_e=False,
                     robustness_level="LOW"):
    """Map a frozen 9M final_status to the closed 9N recommendation
    vocabulary.

    Params
    ------
    oos_status:
        one of the 9M OOS_STATUSES ladder values.
    is_conditional:
        True when the claim is regime-scoped (has a regime_dim / is
        never merged into a universal claim).
    seven_e:
        True when the finding touches the frozen 7E directional NO-GO.
    robustness_level:
        one of ("LOW", "MEDIUM", "HIGH") from the 9M robustness tier.
    """
    if seven_e or oos_status == _oos.OOS_STATUSES[0]:  # BLOCKED
        return _c.RECOMMENDATION_STATUSES[0]           # 7E_BLOCKED

    if oos_status == _oos.OOS_STATUSES[1]:             # UNAVAILABLE
        return _c.RECOMMENDATION_STATUSES[1]           # NO_EVIDENCE
    if oos_status == _oos.OOS_STATUSES[2]:             # INCONCLUSIVE
        return _c.RECOMMENDATION_STATUSES[2]           # INCONCLUSIVE
    if oos_status == _oos.OOS_STATUSES[3]:             # REJECTED
        return _c.RECOMMENDATION_STATUSES[3]           # REJECTED
    if oos_status == _oos.OOS_STATUSES[4]:             # OOS_PARTIAL
        return _c.RECOMMENDATION_STATUSES[4]           # REQUIRES_MORE_OOS

    conditional = bool(is_conditional)

    if oos_status == _oos.OOS_STATUSES[5]:             # OOS_PROMISING
        return (_c.RECOMMENDATION_STATUSES[5]          # CONDITIONAL
                if conditional
                else _c.RECOMMENDATION_STATUSES[6])    # PROMISING

    if oos_status == _oos.OOS_STATUSES[6]:             # OOS_ROBUST
        return (_c.RECOMMENDATION_STATUSES[5]          # CONDITIONAL
                if conditional
                else _c.RECOMMENDATION_STATUSES[6])    # PROMISING

    if oos_status == _oos.OOS_STATUSES[7]:             # VALIDATED_RESEARCH_ONLY
        if conditional:
            return _c.RECOMMENDATION_STATUSES[5]       # CONDITIONAL (scoped)
        if robustness_level != "HIGH":
            # A non-HIGH robustness tier can never reach the top
            # unconditional rung -- it is conservatively PROMISING.
            return _c.RECOMMENDATION_STATUSES[6]       # PROMISING
        return _c.RECOMMENDATION_STATUSES[7]           # ROBUST_RESEARCH_FINDING

    # Defensive fallback: unknown / edge ladder value is conservative.
    return _c.RECOMMENDATION_STATUSES[2]               # INCONCLUSIVE
