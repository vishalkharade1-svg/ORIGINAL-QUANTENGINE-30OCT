"""Sandbox external-evidence gate run (read-only, sanitized).

Builds the canonical ``SandboxExternalEvidenceArtifact`` for the
current working tree using ONLY existing authorities:

* credentials: ``config.settings`` (booleans only -- secret values
  are never read, printed, logged, or serialized);
* endpoints: ``core.exchanges.delta.delta_environments``;
* signing: ``core.exchanges.delta.delta_auth`` (dummy-input shape
  check only);
* client: ``DeltaExchange`` / ``DeltaSignedREST`` (existing client).

Key-only ``.env`` parsing: only variable NAMES (text before ``=``)
are inspected; values never enter this process beyond what
``config.settings`` already holds, and no value is ever emitted.

Minimal probe: if (and only if) ``sandbox_client()`` builds -- i.e.
sandbox credentials are provisioned -- exactly ONE authenticated
read-only GET (wallet balances) is attempted through the existing
client. Otherwise the artifact records the fail-closed refusal with
CONFIGURATION_MISSING and no network is touched.

Output: canonical JSON artifact at
``data/fixtures/delta/sandbox_external_evidence_YYYYMMDD.json`` plus
a sanitized stdout summary (booleans/classifications only).

``is_production_ready`` stays False; production is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.exchanges.delta.sandbox_evidence import (  # noqa: E402
    AccountEvidence,
    Authentication,
    EconomicsEvidence,
    Limitation,
    ObservationContext,
    OrderLifecycleEvidence,
    Provenance,
    Reconciliation,
    Safety,
    SandboxExternalEvidenceArtifact,
)


CLIENT_AUTHORITY = (
    "core.exchanges.delta.delta_exchange.DeltaExchange"
)
SIGNING_AUTHORITY = "core.exchanges.delta.delta_auth"


def _dotenv_keys(path):
    """Variable NAMES present in .env (values never inspected)."""
    keys = set()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return keys
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def _check_signing_authority():
    """Verify the canonical signing shape with dummy inputs only."""
    from core.exchanges.delta.delta_auth import (
        build_prehash,
        query_string,
        sign,
    )

    prehash = build_prehash(
        "GET", "1542110948",
        "/v2/orders" + query_string({"product_id": 1}), "")
    if prehash != "GET1542110948/v2/orders?product_id=1":
        return False
    digest = sign("dummy-secret-never-a-credential", prehash)
    return len(digest) == 64 and all(
        c in "0123456789abcdef" for c in digest)


def _check_endpoints():
    from core.exchanges.delta import delta_environments as env

    sandbox = env.resolve_rest_endpoint("SANDBOX")
    production = env.resolve_rest_endpoint("PRODUCTION")
    return (
        sandbox == env.SANDBOX_REST_URL
        and production == env.PRODUCTION_REST_URL
        and sandbox != production
        and env.is_sandbox_endpoint(sandbox)
        and not env.is_production_endpoint(sandbox)
    )


def _classify_http_failure(status, venue_code):
    """Map an authenticated-read failure to (auth_status, failure).

    Venue categories reuse the existing ``delta_auth`` constants
    (no duplicated literals, no credential-shaped strings).
    """
    from core.exchanges.delta import delta_auth as auth

    if status == 429:
        return "BLOCKED", "RATE_LIMITED"
    if status is not None and 500 <= status <= 599:
        return "BLOCKED", "EXCHANGE_ERROR"
    if status in (401, 403):
        category = auth.classify_auth_error(
            venue_code, http_status=status)
        mapping = {
            auth.INVALID_API_KEY: "AUTHENTICATION_REJECTED",
            auth.INVALID_SIGNATURE: "SIGNATURE_REJECTED",
            auth.TIMESTAMP_ERROR: "TIMESTAMP_REJECTED",
            auth.IP_NOT_WHITELISTED: "IP_NOT_WHITELISTED",
            auth.PERMISSION_DENIED: "AUTHENTICATION_REJECTED",
            auth.AUTHENTICATION_FAILED: "AUTHENTICATION_REJECTED",
        }
        return "REJECTED", mapping.get(category, "AUTHENTICATION_REJECTED")
    return "BLOCKED", "EXCHANGE_ERROR"


def _extract_venue_code(payload):
    """Extract a venue error-code string only (never bodies/values)."""
    try:
        if isinstance(payload, dict):
            for key in ("code", "error_code"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:64]
            nested = payload.get("error")
            if isinstance(nested, dict):
                for key in ("code", "error_code"):
                    value = nested.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()[:64]
            result = payload.get("result")
            if isinstance(result, dict):
                value = result.get("code")
                if isinstance(value, str) and value.strip():
                    return value.strip()[:64]
    except Exception:  # noqa: BLE001 (best-effort code extraction)
        pass
    return None


def run():
    from config.settings import settings
    from core.exchanges.delta import delta_environments as env

    dotenv_keys = _dotenv_keys(REPO_ROOT / ".env")
    env_loaded = bool(dotenv_keys)
    sandbox_vars_present = ("DELTA_SANDBOX_API_KEY" in dotenv_keys
                            and "DELTA_SANDBOX_API_SECRET" in dotenv_keys)
    sandbox_loaded = bool(getattr(settings, "SANDBOX_API_KEY", "")
                          and getattr(settings, "SANDBOX_API_SECRET", ""))
    endpoint_ok = _check_endpoints()
    signing_ok = _check_signing_authority()

    context = ObservationContext(
        endpoint_class="ACCOUNT_READ",
        request_method="GET",
        operation_class="AUTHENTICATED_READ",
        client_authority=CLIENT_AUTHORITY,
    )

    # Minimal sandbox probe through the existing authority only.
    # Production credentials are never substituted: sandbox_client()
    # refuses instead of falling back.
    auth_status = "BLOCKED"
    failure = "CONFIGURATION_MISSING"
    signature_accepted = None
    timestamp_accepted = None
    response_status = None
    exchange_error_code = None
    account = AccountEvidence(
        status="BLOCKED",
        limitations=("authenticated sandbox access not established; "
                     "no account fields observed",),
    )
    order_failure = "CONFIGURATION_MISSING"
    order_status = "BLOCKED"

    try:
        client = env.sandbox_client()
    except Exception:  # noqa: BLE001 (fail-closed refusal is the evidence)
        client = None

    if client is None:
        # Refused pre-transport: no HTTP status exists, nothing was
        # sent, nothing was observed. CONFIGURATION_MISSING (sandbox
        # credential variables absent) -- never invent a venue cause.
        pass
    else:
        try:
            client.get_balance()
        except Exception as exc:  # noqa: BLE001 (classify, never log values)
            status = getattr(getattr(exc, "response", None),
                             "status_code", None)
            if status is None:
                status = getattr(exc, "status_code", None)
            try:
                status = int(status) if status is not None else None
            except (TypeError, ValueError):
                status = None
            venue_code = None
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    venue_code = _extract_venue_code(response.json())
                except Exception:  # noqa: BLE001 (body unreadable)
                    venue_code = None
            name = type(exc).__name__
            if status is None:
                if "Timeout" in name:
                    auth_status, failure = "BLOCKED", "NETWORK_UNAVAILABLE"
                elif "Connect" in name or "Network" in name:
                    auth_status, failure = "BLOCKED", "ENDPOINT_UNAVAILABLE"
                else:
                    auth_status, failure = "BLOCKED", "UNKNOWN"
            elif 200 <= status <= 299:
                auth_status, failure = "VERIFIED", "NONE"
            else:
                auth_status, failure = _classify_http_failure(
                    status, venue_code)
            response_status = status
            exchange_error_code = venue_code
            if auth_status != "VERIFIED":
                order_failure = failure
        else:
            auth_status, failure = "VERIFIED", "NONE"
            response_status = 200
            account = AccountEvidence(
                status="PARTIAL",
                limitations=("authenticated read succeeded; response "
                             "schema not mapped to canonical balance "
                             "fields in this gate",),
            )
            order_failure = "NONE"
            order_status = "NOT_ATTEMPTED"

    authentication = Authentication(
        status=auth_status,
        failure_classification=failure,
        credential_variables_present=bool(sandbox_vars_present),
        credentials_loaded=bool(sandbox_loaded),
        endpoint_selected_correctly=bool(endpoint_ok),
        signing_authority=SIGNING_AUTHORITY if signing_ok else "UNVERIFIED",
        signature_accepted=signature_accepted,
        timestamp_accepted=timestamp_accepted,
    )

    provenance = Provenance(
        authority=CLIENT_AUTHORITY,
        endpoint_class="ACCOUNT_READ",
        operation="authenticated_read",
        response_status=response_status,
        exchange_error_code=exchange_error_code,
        observed_at=None,
    )

    economics = EconomicsEvidence(
        status="NOT_ATTEMPTED",
        limitations=("no economics observation attempted without "
                     "authenticated sandbox access",),
    )

    order_lifecycle = OrderLifecycleEvidence(
        status=order_status,
        attempted=False,
        failure_classification=order_failure,
        limitations=("sandbox identity not established; no order "
                     "lifecycle attempted",),
    )

    reconciliation = Reconciliation(
        status="BLOCKED",
        unavailable_fields=("exchange_product", "exchange_economics",
                            "exchange_account"),
        notes=("no external evidence acquired; nothing compared; "
               "local authorities untouched",),
    )

    limitations = [
        Limitation(
            code="SANDBOX_CREDENTIALS_ABSENT" if client is None
            else "SANDBOX_AUTH_" + auth_status,
            category=("CONFIGURATION" if client is None
                      else "AUTHENTICATION"),
            description=("sandbox credential variables are not "
                         "configured in the local environment; "
                         "sandbox_client() refuses fail-closed without "
                         "substituting production credentials"
                         if client is None else
                         "sandbox authentication probe classified as "
                         "%s/%s" % (auth_status, failure)),
            blocking=True,
        ),
        Limitation(
            code="NO_EXTERNAL_OBSERVATION",
            category="DATA",
            description=("no authenticated sandbox response was "
                         "observed; account/contract/economics evidence "
                         "remains missing, never defaulted"),
            blocking=True,
        ),
        Limitation(
            code="ORDER_LIFECYCLE_NOT_ATTEMPTED",
            category="ORDER_LIFECYCLE",
            description=("sandbox identity not established; no order "
                         "was created, filled, cancelled, or cleaned up"),
            blocking=False,
        ),
        Limitation(
            code="RECONCILIATION_BLOCKED",
            category="RECONCILIATION",
            description=("nothing to compare against local authorities; "
                         "no local authority overridden"),
            blocking=True,
        ),
    ]

    safety = Safety(environment_verified_sandbox=True)

    final = ("SANDBOX_EXTERNAL_EVIDENCE_PARTIAL"
             if auth_status == "VERIFIED"
             else "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")

    artifact = SandboxExternalEvidenceArtifact.create(
        observation_context=context,
        provenance=provenance,
        authentication=authentication,
        account=account,
        contracts=(),
        economics=economics,
        order_lifecycle=order_lifecycle,
        reconciliation=reconciliation,
        limitations=limitations,
        safety=safety,
        final_classification=final,
    )

    out_path = (REPO_ROOT / "data" / "fixtures" / "delta"
                / "sandbox_external_evidence_20260925.json")
    out_path.write_text(artifact.to_json() + "\n", encoding="utf-8")

    print("artifact_id: %s" % artifact.artifact_id)
    print("variables_detected: %s" % ("YES" if sandbox_vars_present else "NO"))
    print(".env loaded: %s" % ("YES" if env_loaded else "NO"))
    print("endpoint correct: %s" % ("YES" if endpoint_ok else "NO"))
    print("signing authority verified: %s" % ("YES" if signing_ok else "NO"))
    print("sandbox authentication: %s/%s" % (auth_status, failure))
    print("http status: %s" % (response_status,))
    print("final: %s" % final)
    print("production_ready: FALSE")
    print("artifact: %s" % out_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
