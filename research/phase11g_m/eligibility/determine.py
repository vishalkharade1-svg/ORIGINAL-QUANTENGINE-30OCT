"""11G-M mechanical D3-eligibility determination (read-only, seal-preserving).

Reads ONLY frozen artifacts (11G-K specs + manifest, 11G-L primary
results). Touches no dataset, opens no holdout, fits nothing. Asserts
the D3 seal counters are 0 before and after (recorded in the output).

Mechanical rule (§9, applied to 11G-L outcomes + frozen policy):
- L verdict FAIL (falsified with sufficient evidence) -> excluded
  (resurrection barred), retained in the multiple-testing denominator.
- L pooled trades == 0 (NO EVIDENCE, zero events) -> not promoted
  (promotion would be discovery, not validation).
- L verdict INSUFFICIENT_EVIDENCE -> proceeds ONLY with explicit
  frozen-methodology permission. Permission is defined as a
  promotion_policy other than "NONE". All 8 frozen policies are
  "NONE" -> no permission -> excluded.
- (Completeness branch: a PASS with non-NONE promotion would be
  eligible. No PASSes exist; branch unreached.)

Output is fully deterministic (no timestamps, no wall clock).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

KDIR = BASE_DIR / "research" / "phase11g_k"
LRES = BASE_DIR / "research" / "phase11g_l" / "results"
OUT = Path(__file__).resolve().parent / "eligibility.json"


def _counters():
    from research.phase11g import datasets as DG
    from research.phase11g import fresh as FR
    return {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
            "D3_LOAD": DG.D3_ACCESS["load"],
            "FR_READ": FR.D3_ACCESS_11GD["read"],
            "FR_HASH": FR.D3_ACCESS_11GD["hash"],
            "FR_LOAD": FR.D3_ACCESS_11GD["load"]}


def _sha256_canonical(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def determine():
    before = _counters()
    assert all(v == 0 for v in before.values()), before
    man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
    prim = json.loads((LRES / "primary_results.json").read_text())
    hyps, eligible = {}, []
    for hid in sorted(prim):
        doc = json.loads((KDIR / "hypotheses" / (hid + ".json")).read_text())
        assert doc["status"] == "FROZEN"
        hhash = hashlib.sha256(
            json.dumps(doc, sort_keys=True).encode()).hexdigest()
        assert hhash == man["hypothesis_hashes"][hid], hid
        promo = doc["promotion_policy"]
        n = prim[hid]["n_pooled"]
        verdict = prim[hid]["verdict"]
        net_c = prim[hid]["metrics_C"]["net"]
        if verdict == "FAIL":
            branch, ok, reason = ("RESURRECTION_BARRED", False,
                                  "11G-L FAIL with sufficient evidence; "
                                  "holdout retest would be resurrection")
        elif n == 0:
            branch, ok, reason = ("ZERO_EVENTS_NOT_PROMOTED", False,
                                  "11G-L zero pooled events; promotion "
                                  "would be discovery, not validation")
        elif verdict == "INSUFFICIENT_EVIDENCE":
            permitted = (promo != "NONE")
            branch = "SUB_ELIGIBLE_PERMISSION_%s" % ("GRANTED" if permitted else "ABSENT")
            ok = permitted
            reason = ("frozen promotion_policy=%r; INSUFFICIENT hypotheses "
                      "proceed only with explicit permission" % promo)
        else:  # PASS (unreached: no 11G-L PASSes exist)
            ok = (promo != "NONE")
            branch = "PASS_PERMISSION_%s" % ("GRANTED" if ok else "ABSENT")
            reason = "promotion_policy=%r" % promo
        hyps[hid] = {"dev_verdict": verdict, "dev_n_pooled": n,
                     "dev_net_C": net_c, "promotion_policy": promo,
                     "hypothesis_hash": hhash, "branch": branch,
                     "eligible": ok, "reason": reason}
        if ok:
            eligible.append(hid)
    after = _counters()
    assert all(v == 0 for v in after.values()), after
    result = {
        "phase": "11G-M",
        "rule": "mechanical §9 on 11G-L outcomes + frozen promotion_policy",
        "freeze_hash": (KDIR / "freeze" / "freeze_hash.txt").read_text().strip(),
        "hypotheses": hyps,
        "eligible_set": sorted(eligible),
        "family_denominator": 8,
        "d3_counters_before": before,
        "d3_counters_after": after,
        "inputs": {
            "primary_results": _sha256_canonical(prim),
            "freeze_manifest": _sha256_canonical(man),
        },
    }
    result["code_hash"] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


if __name__ == "__main__":
    r = determine()
    print(json.dumps({"eligible_set": r["eligible_set"],
                      "family_denominator": r["family_denominator"],
                      "branches": {h: v["branch"] for h, v in r["hypotheses"].items()}},
                     indent=1, sort_keys=True))
