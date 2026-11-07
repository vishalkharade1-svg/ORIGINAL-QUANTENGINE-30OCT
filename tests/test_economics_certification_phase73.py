from research.economics.economics_certification import assess


def test_missing_real_economics_is_blocked():
    c = assess()
    assert not c.certifiable
    assert "real venue fee evidence is missing" in c.reasons
    assert "realized fill/slippage evidence is missing" in c.reasons


def test_orderbook_snapshot_alone_cannot_certify_slippage():
    class A:
        provenance_status = "REAL"
        evidence_sha256 = "fee"
    class F:
        provenance_status = "REAL"
        funding_evidence_sha256 = "fund"
    class O:
        provenance_status = "REAL"
        evidence_sha256 = "book"
    c = assess(fee_artifact=A(), funding_artifact=F(), market_friction_artifact=O())
    assert not c.certifiable
    assert "realized fill/slippage evidence is missing" in c.reasons


def test_complete_real_evidence_is_certifiable():
    class A:
        provenance_status = "REAL"; evidence_sha256 = "fee"
    class F:
        provenance_status = "REAL"; funding_evidence_sha256 = "fund"
    class O:
        provenance_status = "REAL"; evidence_sha256 = "book"
    class R:
        provenance_status = "REAL"
    c = assess(fee_artifact=A(), funding_artifact=F(), market_friction_artifact=O(), realized_fill_artifact=R())
    assert c.certifiable
    assert c.status == "CERTIFIABLE"
