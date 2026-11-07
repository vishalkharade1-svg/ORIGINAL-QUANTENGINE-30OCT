#!/usr/bin/env python3
"""Audit whether a genuine frozen 9L report can be admitted to 9M.

This is an offline, read-only audit. It never invents a report, selects a
finding, creates a preregistration, or accesses the network.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from core.research.conditional_ml.report import ConditionalMlReport
from core.research.conditional_ml.types import ENTRY_SELECTION_SUPPORTED, RECOVERY_SUPPORTED

DEFAULT=ROOT/'research/results/phase49_9l_real_discovery.json'
OUT=ROOT/'research/results/phase60_9l_admission_readiness.json'

def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--report', type=Path, default=DEFAULT)
    ap.add_argument('--output', type=Path, default=OUT)
    args=ap.parse_args()
    report_path=args.report if args.report.is_absolute() else ROOT/args.report
    result={'schema':'phase60-9l-admission-readiness-v1','report_path':str(report_path),'production_ready':False}
    if not report_path.exists():
        result.update(status='MISSING_GENUINE_9L_REPORT',eligible_entry_selection=0,eligible_recovery=0,total_eligible=0,preregistration_created=False,reason='Original genuine Phase-49 9L report artifact is unavailable; no report is synthesized.')
    else:
        payload=json.loads(report_path.read_text(encoding='utf-8'))
        report=ConditionalMlReport.from_dict(payload)
        emission=report.emission_check()
        entry=sum(1 for f in report.entry_selection if f.status==ENTRY_SELECTION_SUPPORTED and f.survives_familywise and f.selected)
        recovery=sum(1 for f in report.recovery if f.status==RECOVERY_SUPPORTED and f.survives_familywise)
        total=entry+recovery
        result.update(status='ELIGIBLE_FINDINGS_AVAILABLE' if total else 'NO_ELIGIBLE_HYPOTHESES',report_id=report.report_id,eligible_entry_selection=entry,eligible_recovery=recovery,total_eligible=total,emission_clean=emission['clean'],preregistration_created=False,reason='Eligibility is audited only; explicit human/research-layer admission remains a separate step.')
    result['content_identity']=hashlib.sha256(canonical(result)).hexdigest()
    out=args.output if args.output.is_absolute() else ROOT/args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
