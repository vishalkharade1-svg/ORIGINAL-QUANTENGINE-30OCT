from dataclasses import replace
from core.governance.production_hardening_stages76_79 import (
    EvidenceRetention, DataLineagePackage, SupplyChainAssurance, TabletopExercise,
    evaluate_evidence_retention, evaluate_data_lineage, evaluate_supply_chain_assurance,
    evaluate_tabletop_exercise,
)

def retention():
    return EvidenceRetention("policy","schedule","classification","holds","authority","assessment",
        "2026-11-09T10:00:00Z",10,10,10,2,0,2,True,True)

def lineage():
    return DataLineagePackage("package","sources","transforms","environment","repro-report","reproduction",
        "2026-11-09T10:00:00Z",5,5,7,7,0,0,True,True)

def supply():
    return SupplyChainAssurance("assurance","sbom","provenance","attestations","vulns","review",
        "2026-11-09T10:00:00Z",12,12,12,0,0,0,True,True)

def tabletop():
    return TabletopExercise("exercise","scenario","participants","objectives","outcomes","remediations","observer",
        "2026-11-09T10:00:00Z",4,4,3,3,3,0,True,True,False)

def test_complete_assessments_are_unverified_and_never_arm():
    results = [evaluate_evidence_retention(retention()), evaluate_data_lineage(lineage()),
               evaluate_supply_chain_assurance(supply()), evaluate_tabletop_exercise(tabletop())]
    assert [x.stage for x in results] == [76,77,78,79]
    assert all(x.status.endswith("COMPLETE_UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_retention_gaps_and_unauthorized_disposition_hold():
    result = evaluate_evidence_retention(replace(retention(), artifacts_with_retention_rule=9, unauthorized_dispositions=1))
    assert result.status == "EVIDENCE_RETENTION_HOLD"
    assert len(result.reasons) >= 2

def test_lineage_requires_full_source_and_transform_coverage():
    result = evaluate_data_lineage(replace(lineage(), sources_identified=4, transformations_documented=6))
    assert result.status == "DATA_LINEAGE_HOLD"
    assert len(result.reasons) >= 2

def test_supply_chain_requires_complete_sbom_and_vulnerability_disposition():
    result = evaluate_supply_chain_assurance(replace(supply(), components_in_sbom=11, high_vulnerabilities_open=1))
    assert result.status == "SUPPLY_CHAIN_ASSURANCE_HOLD"
    assert len(result.reasons) >= 2

def test_tabletop_cannot_execute_operational_actions_and_needs_remediation():
    result = evaluate_tabletop_exercise(replace(tabletop(), operational_actions_executed=True, findings_with_owner=2))
    assert result.status == "TABLETOP_EXERCISE_HOLD"
    assert len(result.reasons) >= 2
