"""Deterministic evidence-closure matrix (read-only).

Records every remaining certification blocker with its exact claim,
required evidence, current evidence, readiness states, and closure
condition. Statuses use the closed vocabulary only; readiness states
distinguish CODE_READY / TEST_READY / EVIDENCE_READY /
EVIDENCE_AVAILABLE / EVIDENCE_VERIFIED and never collapse them.

All rows use explicit keyword arguments so field mapping is auditable.

Usage:
    python scripts/evidence_closure_matrix.py --json
    python scripts/evidence_closure_matrix.py --text

Deterministic: fixed row order, sorted keys, no clock/random/UUID.
Read-only: never writes pins, fixtures, or artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys


STATUSES = (
    "VERIFIED", "PARTIAL", "LOCAL_VERIFIED", "UNVERIFIED",
    "NOT_OBSERVED", "BLOCKED", "UNWIRED", "OPERATOR_CONTROLLED",
)

READINESS = (
    "CODE_READY", "TEST_READY", "EVIDENCE_READY",
    "EVIDENCE_AVAILABLE", "EVIDENCE_VERIFIED", "EVIDENCE_UNAVAILABLE",
)

FIELDS = (
    "blocker_id", "capability", "claim", "evidence_required",
    "evidence_currently_available", "evidence_type",
    "authoritative_source_required", "repository_capture_mechanism",
    "parser_support_status", "test_status", "external_dependency",
    "closure_condition", "current_status", "code_readiness",
    "test_readiness", "evidence_readiness", "owner_action_required",
    "reason_blocked",
)

CAPTURE = ("scripts/capture_delta_public_frames.py (bounded, "
           "credential-free public capture)")
VERIFIER = "scripts/verify_delta_global_evidence.py"
NO_CAPTURE = "none (no venue capture performed for this blocker)"
UNAUDITED_META = "Delta product/metadata endpoint (unaudited; no fetch made)"


def build_matrix() -> list[dict]:
    return [
        {
            "blocker_id": "global-rollover",
            "capability": "Global rollover",
            "claim": "Consecutive-cst 1m rollover observed in one session",
            "evidence_required": "genuine Global frames showing an actual "
            "instrument/session rollover transition with identity both "
            "sides + timestamps + continuity",
            "evidence_currently_available": "candle/trade schemas, "
            "subscription echo, duplicates, client reconnect, three "
            "silence samples (negative evidence)",
            "evidence_type": "GENUINE_VENUE_OBSERVATION",
            "authoritative_source_required":
            "wss://public-socket.delta.exchange",
            "repository_capture_mechanism": CAPTURE,
            "parser_support_status": "verifier implemented; reports "
            "BLOCKED on partials",
            "test_status": "gate + fixture tests pin BLOCKED",
            "external_dependency": "market publication timing",
            "closure_condition": "qualifying bounded capture passing "
            "the verifier",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: run boundary-timed "
            "capture until transition observed",
            "reason_blocked": "sparse publication (~1 burst per 5-6 "
            "min); no transition in ~25 min historical + 150s + 330s "
            "fresh windows",
        },
        {
            "blocker_id": "server-recovery",
            "capability": "Server recovery",
            "claim": "Server disconnect detected, reconnected, "
            "resubscribed, authoritative data resumed without corruption",
            "evidence_required": "genuine server-side disconnect with "
            "detection, reconnect, resubscribe, resumed data, "
            "duplicate/stale audit",
            "evidence_currently_available": "client-initiated "
            "close/reconnect drills only",
            "evidence_type": "GENUINE_VENUE_OBSERVATION",
            "authoritative_source_required": "provider-initiated "
            "disconnect",
            "repository_capture_mechanism": "capture utility closes are "
            "client-initiated by design",
            "parser_support_status": "no server-event parser exists "
            "(nothing to parse)",
            "test_status": "client-reconnect tests pin client-only "
            "semantics",
            "external_dependency": "provider outage occurrence",
            "closure_condition": "observed server event with full "
            "recovery audit",
            "current_status": "NOT_OBSERVED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: capture a genuine "
            "provider disconnect if one occurs; never sabotage the link",
            "reason_blocked": "implementation ready (reconnect SM, "
            "resub, dup suppression, session gate, DQ gate); venue "
            "event never observed",
        },
        {
            "blocker_id": "candle-finality",
            "capability": "Candle finality",
            "claim": "Authoritative venue candle-close semantics",
            "evidence_required": "venue close flag / state / update "
            "semantics in genuine frames",
            "evidence_currently_available": "no finality field in any "
            "genuine India/Global frame",
            "evidence_type": "GENUINE_VENUE_OBSERVATION",
            "authoritative_source_required": "Delta public channel "
            "docs/frames",
            "repository_capture_mechanism": CAPTURE,
            "parser_support_status": "no finality parser (nothing to "
            "parse)",
            "test_status": "local-policy tests (finality tracker, "
            "bridge, dispatch)",
            "external_dependency": "venue field documentation or "
            "observation",
            "closure_condition": "observed close semantics",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: confirm absence with "
            "provider docs or capture",
            "reason_blocked": "local closed-candle policy VERIFIED; "
            "venue finality absent",
        },
        {
            "blocker_id": "sequence-semantics",
            "capability": "Sequence semantics",
            "claim": "Authoritative venue ordering/sequence semantics",
            "evidence_required": "explicit sequence / monotonic id / "
            "ordering + gap semantics",
            "evidence_currently_available": "no sequence in any genuine "
            "frame; receipt order explicitly not a sequence",
            "evidence_type": "GENUINE_VENUE_OBSERVATION",
            "authoritative_source_required": "Delta public channel "
            "docs/frames",
            "repository_capture_mechanism": CAPTURE,
            "parser_support_status": "no sequence parser (nothing to "
            "parse)",
            "test_status": "continuity-tracker fail-closed tests",
            "external_dependency": "venue field documentation or "
            "observation",
            "closure_condition": "observed sequence semantics",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: confirm absence with "
            "provider docs or capture",
            "reason_blocked": "fail-closed continuity proven; venue "
            "sequence absent",
        },
        {
            "blocker_id": "contract-tick-size",
            "capability": "Contract tick size",
            "claim": "Venue-authoritative tick size consumed at runtime",
            "evidence_required": "instrument, field, observed value, "
            "parser, consumer, enforcement, test",
            "evidence_currently_available": "constants in source only; "
            "no venue observation",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta product/metadata "
            "endpoint",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no venue contract parser wired "
            "to runtime",
            "test_status": "boundary pins prove UNWIRED",
            "external_dependency": "provider metadata access",
            "closure_condition": "authoritative value ingested, "
            "validated, enforced, tested",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "product specification",
            "reason_blocked": "defined in fragments; source "
            "unverified; runtime unwired",
        },
        {
            "blocker_id": "contract-multiplier",
            "capability": "Contract multiplier",
            "claim": "Venue-authoritative multiplier consumed at runtime",
            "evidence_required": "instrument, field, observed value, "
            "parser, consumer, enforcement, test",
            "evidence_currently_available": "metadata key read in "
            "factory; no venue observation",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta product/metadata "
            "endpoint",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "factory reads unverified metadata "
            "only",
            "test_status": "boundary pins prove UNWIRED",
            "external_dependency": "provider metadata access",
            "closure_condition": "authoritative value ingested, "
            "validated, enforced, tested",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "product specification",
            "reason_blocked": "values must not be invented or "
            "remembered",
        },
        {
            "blocker_id": "contract-qty-step",
            "capability": "Contract quantity step",
            "claim": "Venue-authoritative quantity increment consumed "
            "at runtime",
            "evidence_required": "instrument, field, observed value, "
            "parser, consumer, enforcement, test",
            "evidence_currently_available": "local QUANTITY_PRECISION "
            "only; no venue observation",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta product/metadata "
            "endpoint",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no venue quantity parser wired "
            "to runtime",
            "test_status": "boundary pins prove UNWIRED",
            "external_dependency": "provider metadata access",
            "closure_condition": "authoritative value ingested, "
            "validated, enforced, tested",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "product specification",
            "reason_blocked": "local precision is not venue "
            "verification",
        },
        {
            "blocker_id": "contract-min-qty",
            "capability": "Contract minimum quantity",
            "claim": "Venue-authoritative minimum quantity enforced at "
            "runtime",
            "evidence_required": "instrument, field, observed value, "
            "parser, consumer, enforcement, test",
            "evidence_currently_available": "local MIN_QUANTITY dust "
            "rule only; no venue observation",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta product/metadata "
            "endpoint",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no venue minimum parser wired to "
            "runtime",
            "test_status": "boundary pins prove UNWIRED",
            "external_dependency": "provider metadata access",
            "closure_condition": "authoritative value ingested, "
            "validated, enforced, tested",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "product specification",
            "reason_blocked": "dust rule is local hygiene, not venue "
            "proof",
        },
        {
            "blocker_id": "contract-settlement-margin",
            "capability": "Contract settlement/margin",
            "claim": "Venue settlement, expiry/rollover, "
            "margin/leverage semantics",
            "evidence_required": "authoritative spec paragraphs per "
            "instrument with version",
            "evidence_currently_available": "none",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta product/metadata "
            "endpoint",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no parser",
            "test_status": "none (correctly absent)",
            "external_dependency": "provider specification access",
            "closure_condition": "authoritative spec ingested and "
            "enforced",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "specification",
            "reason_blocked": "no venue source consulted to date",
        },
        {
            "blocker_id": "economics-fees",
            "capability": "Economics maker/taker fees",
            "claim": "Venue-authoritative fee schedule enforced at "
            "runtime",
            "evidence_required": "maker/taker fees per instrument with "
            "source + version",
            "evidence_currently_available": "formula + explicit-zero "
            "defaults; no venue values",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "Delta fee schedule "
            "endpoint/docs",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "CostSpec math frozen; values "
            "settings-backed",
            "test_status": "formula/symmetry/single-subtraction tests",
            "external_dependency": "provider fee schedule access",
            "closure_condition": "authoritative fees ingested and "
            "enforced; UNKNOWN kept distinct from EXPLICIT_ZERO",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain authoritative "
            "fee schedule",
            "reason_blocked": "zero defaults are explicit, never "
            "realistic-by-default",
        },
        {
            "blocker_id": "economics-slippage",
            "capability": "Economics slippage model",
            "claim": "Verified slippage assumptions enforced at runtime",
            "evidence_required": "slippage model assumptions with "
            "source + version",
            "evidence_currently_available": "bps formula with settings "
            "values; model unverified",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "execution-quality "
            "observation",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "CostSpec math frozen",
            "test_status": "formula/symmetry tests",
            "external_dependency": "execution-quality evidence",
            "closure_condition": "verified slippage model enforced",
            "current_status": "UNVERIFIED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: obtain "
            "execution-quality evidence",
            "reason_blocked": "formula verified; model assumptions "
            "unverified",
        },
        {
            "blocker_id": "economics-gates",
            "capability": "Economics runtime gates",
            "claim": "require_realistic/apply_costs enforced on the "
            "runtime path",
            "evidence_required": "wired gate with verified venue inputs",
            "evidence_currently_available": "DEFINED + tested, zero "
            "runtime callers (call-site proven)",
            "evidence_type": "AUTHORITATIVE_VENUE_SPEC",
            "authoritative_source_required": "verified venue inputs "
            "first",
            "repository_capture_mechanism": "n/a (internal seam)",
            "parser_support_status": "gates implemented",
            "test_status": "boundary pins prove UNWIRED",
            "external_dependency": "verified venue inputs first",
            "closure_condition": "gates wired with verified inputs, "
            "refusals tested",
            "current_status": "UNWIRED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "integrate only after "
            "contract/economics evidence exists",
            "reason_blocked": "wiring without inputs would invent "
            "enforcement",
        },
        {
            "blocker_id": "private-orders",
            "capability": "Private orders",
            "claim": "Authorized order lifecycle evidence "
            "(accepted/rejected/cancelled/expired/partial/filled/"
            "duplicate/unknown)",
            "evidence_required": "genuine private frames or sandbox "
            "observations per state",
            "evidence_currently_available": "none; open_orders() parses "
            "tolerantly but no verdict consumes it",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "tolerant parser, unwired to "
            "verdicts",
            "test_status": "LOCAL tolerant-parse pin only",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "per-state genuine evidence",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox + schemas",
            "reason_blocked": "IMPLEMENTED / UNWIRED parser; mocks are "
            "not evidence",
        },
        {
            "blocker_id": "private-fills",
            "capability": "Private fills",
            "claim": "Authorized fill evidence (fill/order IDs, qty, "
            "price, fee, ts)",
            "evidence_required": "genuine fill records per field",
            "evidence_currently_available": "none",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no fill parser",
            "test_status": "none (correctly absent)",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "per-field genuine evidence",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox + schemas",
            "reason_blocked": "no fill schema observed or assumed",
        },
        {
            "blocker_id": "private-positions",
            "capability": "Private positions",
            "claim": "Authorized position evidence (side/qty/avg/"
            "realized/unrealized)",
            "evidence_required": "genuine position snapshots",
            "evidence_currently_available": "none (fake-executor "
            "drills only)",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "comparison core exists; feed is "
            "fake in tests",
            "test_status": "LOCAL drills only",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "genuine snapshots reconciled",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox + schemas",
            "reason_blocked": "comparison logic LOCAL_VERIFIED; feed "
            "unverified",
        },
        {
            "blocker_id": "private-balances",
            "capability": "Private balances",
            "claim": "Authorized balance evidence (equity/available/"
            "margin/ccy)",
            "evidence_required": "genuine balance snapshots",
            "evidence_currently_available": "none",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "BalanceDivergenceHalt exists; "
            "feed unverified",
            "test_status": "LOCAL gate tests only",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "genuine balances reconciled",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox + schemas",
            "reason_blocked": "exchange state authoritative by "
            "design, never observed",
        },
        {
            "blocker_id": "private-cancellations",
            "capability": "Private cancellations",
            "claim": "Authorized cancellation evidence and handling",
            "evidence_required": "genuine cancelled-order observations",
            "evidence_currently_available": "none",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "no cancellation parser",
            "test_status": "none (correctly absent)",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "genuine cancellation evidence",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox + schemas",
            "reason_blocked": "no cancellation schema observed or "
            "assumed",
        },
        {
            "blocker_id": "private-restart",
            "capability": "Private restart recovery",
            "claim": "Persisted local state + remote snapshot reconciled "
            "after restart with safe halt/continue",
            "evidence_required": "genuine restart against authoritative "
            "remote state",
            "evidence_currently_available": "journal seam drills with "
            "fake executor (LOCAL only)",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet with "
            "schemas",
            "repository_capture_mechanism": "snapshot journal + sandbox "
            "feed",
            "parser_support_status": "persist/load/startup_check "
            "implemented",
            "test_status": "LOCAL restart drills",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "genuine restart drill",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox for live drill",
            "reason_blocked": "halt-on-divergence proven locally; "
            "venue side unproven",
        },
        {
            "blocker_id": "reconciliation-venue",
            "capability": "Venue reconciliation",
            "claim": "Remote state parsed, normalized, reconciled to a "
            "safety verdict end-to-end against genuine venue state",
            "evidence_required": "genuine remote state through the full "
            "chain",
            "evidence_currently_available": "full local chain with fake "
            "feeds (LOCAL_VERIFIED)",
            "evidence_type": "AUTHORIZED_PRIVATE_ACCESS",
            "authoritative_source_required": "sandbox/testnet feed",
            "repository_capture_mechanism": NO_CAPTURE,
            "parser_support_status": "parser exists; open_orders "
            "unwired to verdicts",
            "test_status": "LOCAL case pins",
            "external_dependency": "credentials + sandbox",
            "closure_condition": "end-to-end genuine reconciliation",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: provision authorized "
            "sandbox feed",
            "reason_blocked": "parser existence is not reconciliation "
            "proof",
        },
        {
            "blocker_id": "digest-recert",
            "capability": "Strategy digest re-certification",
            "claim": "Recorded digest re-registered against canonical "
            "source with research re-executed under it",
            "evidence_required": "canonical dataset + historical source "
            "+ execution + reports + statistical outputs + review",
            "evidence_currently_available": "read-only procedure + "
            "forensic baseline; canonical OOS datasets git-ignored "
            "(absent from clean checkout)",
            "evidence_type": "RESEARCH_PROTOCOL_ACCESS",
            "authoritative_source_required": "canonical dataset + "
            "compute + review",
            "repository_capture_mechanism":
            "scripts/recertify_strategy_digest.py (read-only)",
            "parser_support_status": "canonical construction pinned",
            "test_status": "procedure + forensic tests",
            "external_dependency": "dataset + compute + review",
            "closure_condition": "re-executed research recorded under "
            "new digest",
            "current_status": "BLOCKED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "owner: restore canonical dataset, "
            "re-execute research, deliberately re-register",
            "reason_blocked": "mint bytes unrecorded; gate-80 findings "
            "need re-execution; no silent re-pin permitted",
        },
        {
            "blocker_id": "credential-rotation",
            "capability": "Credential rotation",
            "claim": "Automated credential lifecycle "
            "(rotation/revocation proof)",
            "evidence_required": "rotation events / provider revocation "
            "records",
            "evidence_currently_available": "env-backed loading, "
            "blank-gating, redaction (guards verified); rotation "
            "runbook-only",
            "evidence_type": "PROVIDER_OPERATOR",
            "authoritative_source_required": "provider operator",
            "repository_capture_mechanism": "n/a (operator procedure)",
            "parser_support_status": "gate + banner verified "
            "secret-free",
            "test_status": "guard tests green",
            "external_dependency": "provider operator action",
            "closure_condition": "demonstrated rotation",
            "current_status": "OPERATOR_CONTROLLED",
            "code_readiness": "CODE_READY",
            "test_readiness": "TEST_READY",
            "evidence_readiness": "EVIDENCE_UNAVAILABLE",
            "owner_action_required": "operator: rotate/revoke per "
            "incident runbook; no repo subsystem will be built for this",
            "reason_blocked": "intentionally operator-owned; "
            "automation out of scope",
        },
    ]


def serialize(matrix: list[dict]) -> str:
    return json.dumps(matrix, indent=2, sort_keys=True) + "\n"


def render_text(matrix: list[dict]) -> str:
    lines = []
    for row in matrix:
        lines.append("=" * 72)
        lines.append("BLOCKER: %s [%s]" % (
            row["blocker_id"], row["current_status"]))
        lines.append("claim: %s" % row["claim"])
        lines.append("requires: %s" % row["evidence_required"])
        lines.append("available: %s" % row["evidence_currently_available"])
        lines.append("readiness: code=%s test=%s evidence=%s" % (
            row["code_readiness"], row["test_readiness"],
            row["evidence_readiness"]))
        lines.append("closure: %s" % row["closure_condition"])
        lines.append("action: %s" % row["owner_action_required"])
        lines.append("blocked-because: %s" % row["reason_blocked"])
    lines.append("=" * 72)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    matrix = build_matrix()
    if args.json:
        sys.stdout.write(serialize(matrix))
    else:
        sys.stdout.write(render_text(matrix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
