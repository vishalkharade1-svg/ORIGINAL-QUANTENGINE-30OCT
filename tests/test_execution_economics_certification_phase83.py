from types import SimpleNamespace
from research.economics.execution_economics_certification import assess


def art(symbol="BTCUSD", venue="delta", status="REAL", sha="x", **kw):
    vals = dict(symbol=symbol, venue=venue, provenance_status=status, evidence_sha256=sha); vals.update(kw); return SimpleNamespace(**vals)


def complete(**overrides):
    fee = art(coverage_start_ms=1_000, coverage_end_ms=9_000)
    funding = art(funding_evidence_sha256="fund", coverage_start_ms=1_000, coverage_end_ms=9_000)
    friction = art(evidence_sha256="book", start_timestamp_ms=1_000, end_timestamp_ms=9_000)
    fill = art(evidence_sha256="fill", environment="TESTNET", fills=({"fill_id":"f1","timestamp":5_000},))
    binding = {"status":"MATCHED", "fill_count":1, "fill_evidence_sha256":"fill", "friction_evidence_sha256":"book", "binding_sha256":"bind"}
    vals = dict(fee_artifact=fee, funding_artifact=funding, friction_artifact=friction,
                fill_artifact=fill, fill_friction_binding=binding, environment="TESTNET",
                symbol="BTCUSD", oos_start=1_000, oos_end=9_000)
    vals.update(overrides)
    return assess(**vals)


def test_complete_cross_bound_economics_is_certifiable():
    c = complete()
    assert c.certifiable
    assert c.status == "CERTIFIABLE"
    assert c.binding_sha256 == "bind"


def test_missing_historical_fee_window_blocks_oos():
    fee = art()
    c = complete(fee_artifact=fee)
    assert not c.certifiable
    assert "historical OOS fee coverage window is missing" in c.reasons


def test_symbol_mismatch_blocks():
    c = complete(friction_artifact=art(symbol="ETHUSD", evidence_sha256="book", start_timestamp_ms=1_000, end_timestamp_ms=9_000))
    assert not c.certifiable
    assert "friction symbol mismatch" in c.reasons


def test_binding_hash_mismatch_blocks():
    c = complete(fill_friction_binding={"status":"MATCHED", "fill_count":1, "fill_evidence_sha256":"other", "friction_evidence_sha256":"book"})
    assert not c.certifiable
    assert "fill/friction binding references a different fill artifact" in c.reasons


def test_fixture_cannot_certify():
    c = complete(fill_artifact=art(environment="TESTNET", provenance_status="FIXTURE", evidence_sha256="fill", fills=({"fill_id":"f1","timestamp":5_000},)))
    assert not c.certifiable
    assert "fill evidence is not genuine venue evidence" in c.reasons
