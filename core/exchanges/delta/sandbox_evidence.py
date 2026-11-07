"""Canonical sandbox external-evidence artifact (single schema authority).

This module is the ONE canonical model for sandbox external-evidence
artifacts. Do not create a competing evidence schema: adapt this one.

Design rules (schema authority):

* ``environment`` and ``venue`` exist only at the top level
  (``SANDBOX`` / ``DELTA``); they are never duplicated into
  ``observation_context``.
* All source/provenance lives in ONE top-level ``provenance``
  object; account/contract/economics sections carry no ``source``.
* Authentication has its own closed status vocabulary (it is not
  an evidence status); ``failure_classification`` explains WHY an
  operation failed and never contains ``VERIFIED`` (success uses
  ``NONE``).
* ``null`` means unavailable/not observed -- never zero. An
  explicitly observed zero stays ``0``. ``[]`` means no items were
  recorded. ``NOT_ATTEMPTED`` / ``UNAVAILABLE`` / ``BLOCKED`` keep
  their distinct meanings.
* ``observed_at`` is evidence metadata only; it never enters the
  deterministic identity.
* ``is_production_ready`` is hard-wired ``False`` and can never be
  supplied as ``True``; ``local_authority_overridden`` is hard-wired
  ``False``. External evidence never promotes production readiness
  and never overwrites local authority.

Deterministic identity reuses the repository's existing stable hash
authority (``research.phase11g.provenance.model.content_hash`` --
the same authority ``core/research/acquisition/provenance.py``
reuses). No second hashing utility is introduced.

Secret safety: the artifact carries only booleans about
credentials (``credential_variables_present`` /
``credentials_loaded``), never values. Construction scans the
canonical payload for forbidden credential field names and for
caller-declared secret values and refuses before serialization.

Research/evidence only. Sandbox only. Immutable after construction.
"""

from __future__ import annotations

import dataclasses
import json
from decimal import Decimal, InvalidOperation

from research.phase11g.provenance.model import content_hash


SCHEMA_VERSION = "1"
ARTIFACT_TYPE = "SANDBOX_EXTERNAL_EVIDENCE"
ENVIRONMENT = "SANDBOX"
VENUE = "DELTA"
IDENTITY_ALGORITHM = (
    "content_hash:research.phase11g.provenance.model:"
    "sha256-canonical-json"
)

FINAL_VERIFIED = "SANDBOX_EXTERNAL_EVIDENCE_VERIFIED"
FINAL_PARTIAL = "SANDBOX_EXTERNAL_EVIDENCE_PARTIAL"
FINAL_BLOCKED = "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED"

FINAL_CLASSIFICATIONS = (FINAL_VERIFIED, FINAL_PARTIAL, FINAL_BLOCKED)

REQUEST_METHODS = ("GET", "POST")

OPERATION_CLASSES = (
    "AUTHENTICATED_READ",
    "PRODUCT_READ",
    "ECONOMICS_READ",
    "ORDER_LIFECYCLE",
    "RECONCILIATION",
)

AUTH_STATUSES = (
    "VERIFIED",
    "REJECTED",
    "BLOCKED",
    "UNAVAILABLE",
    "NOT_ATTEMPTED",
)

FAILURE_CLASSIFICATIONS = (
    "NONE",
    "CONFIGURATION_MISSING",
    "CONFIGURATION_INVALID",
    "ENV_NOT_LOADED",
    "ENDPOINT_MISCONFIGURED",
    "AUTHENTICATION_REJECTED",
    "SIGNATURE_REJECTED",
    "TIMESTAMP_REJECTED",
    "IP_NOT_WHITELISTED",
    "NETWORK_UNAVAILABLE",
    "ENDPOINT_UNAVAILABLE",
    "RATE_LIMITED",
    "EXCHANGE_ERROR",
    "UNSUPPORTED",
    "UNKNOWN",
)

EVIDENCE_STATUSES = (
    "VERIFIED",
    "PARTIAL",
    "UNAVAILABLE",
    "BLOCKED",
    "NOT_ATTEMPTED",
    "NOT_APPLICABLE",
)

RECONCILIATION_STATUSES = (
    "VERIFIED",
    "MISMATCH",
    "PARTIAL",
    "BLOCKED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
)

LIMITATION_CATEGORIES = (
    "DATA",
    "AUTHENTICATION",
    "CONTRACT",
    "ECONOMICS",
    "ORDER_LIFECYCLE",
    "RECONCILIATION",
    "PROVIDER",
    "CONFIGURATION",
    "SAFETY",
)

#: Exact field names that must never appear in the artifact (keys).
FORBIDDEN_FIELD_NAMES = frozenset({
    "api_key",
    "api_secret",
    "secret",
    "password",
    "token",
    "authorization",
    "authorization_header",
    "signature",
    "signature_value",
    "private_key",
    "access_token",
    "refresh_token",
})

#: Credential-name stems used ONLY as part of an assignment-pattern
#: check (see below). Naming a public configuration variable in
#: prose (e.g. "sandbox credential variables are not configured")
#: is not a leak; assigning it a value is.
_CREDENTIAL_ASSIGNMENT_RE = None  # compiled lazily in _check_value


def _credential_assignment_re():
    global _CREDENTIAL_ASSIGNMENT_RE
    if _CREDENTIAL_ASSIGNMENT_RE is None:
        import re
        stems = (r"api[_-]?key", r"api[_-]?secret", r"private[_-]?key",
                 r"authorization[_-]?header", r"signature[_-]?value",
                 r"access[_-]?token", r"refresh[_-]?token")
        _CREDENTIAL_ASSIGNMENT_RE = re.compile(
            r'(?i)(?:%s)["\x27]?\s*[:=]\s*(\S+)' % "|".join(stems))
    return _CREDENTIAL_ASSIGNMENT_RE


class ArtifactError(ValueError):
    """A sandbox-evidence artifact (or section) is invalid."""


class SecretLeakError(ArtifactError):
    """Forbidden credential material was detected pre-serialization."""


# -------------------------------------------------
# Coercion helpers (single interpretation of numerics)
# -------------------------------------------------

def _to_decimal(value, field):
    """Canonical numeric: Decimal/int/str -> Decimal; None stays None.

    Floats are refused: binary-float rendering is not a canonical
    exchange representation (callers must pass the observed string).
    Bools are refused.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ArtifactError("%s must be Decimal/int/str, got bool" % field)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ArtifactError(
                "%s is not a decimal string: %r" % (field, value))
    raise ArtifactError(
        "%s must be Decimal/int/str or null, got %s"
        % (field, type(value).__name__))


def _to_int(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactError(
            "%s must be int or null, got %s"
            % (field, type(value).__name__))
    return value


def _req_bool(value, field):
    if not isinstance(value, bool):
        raise ArtifactError(
            "%s must be bool, got %s" % (field, type(value).__name__))
    return value


def _req_str(value, field, allowed=None):
    if not isinstance(value, str):
        raise ArtifactError(
            "%s must be str, got %s" % (field, type(value).__name__))
    if allowed is not None and value not in allowed:
        raise ArtifactError("%s has invalid value %r" % (field, value))
    return value


def _opt_str(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ArtifactError(
            "%s must be str or null, got %s"
            % (field, type(value).__name__))
    return value


def _opt_bool(value, field):
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ArtifactError(
            "%s must be bool or null, got %s"
            % (field, type(value).__name__))
    return value


def _tuple_of_str(value, field):
    if value is None:
        raise ArtifactError("%s must be a tuple/list, got None" % field)
    if isinstance(value, (tuple, list)):
        items = tuple(value)
    else:
        raise ArtifactError(
            "%s must be a tuple/list, got %s"
            % (field, type(value).__name__))
    for item in items:
        if not isinstance(item, str):
            raise ArtifactError(
                "%s items must be str, got %s"
                % (field, type(item).__name__))
    return items


def _check_closed(value, field, allowed):
    if value not in allowed:
        raise ArtifactError("%s has invalid value %r" % (field, value))
    return value


# -------------------------------------------------
# Sections (all frozen/immutable)
# -------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ObservationContext:
    endpoint_class: str
    request_method: str
    operation_class: str
    client_authority: str

    def __post_init__(self):
        _req_str(self.endpoint_class, "observation_context.endpoint_class")
        if not self.endpoint_class.strip():
            raise ArtifactError(
                "observation_context.endpoint_class must not be blank")
        _check_closed(self.request_method,
                      "observation_context.request_method", REQUEST_METHODS)
        _check_closed(self.operation_class,
                      "observation_context.operation_class",
                      OPERATION_CLASSES)
        _req_str(self.client_authority,
                 "observation_context.client_authority")
        if not self.client_authority.strip():
            raise ArtifactError(
                "observation_context.client_authority must not be blank")

    def to_dict(self):
        return {
            "endpoint_class": self.endpoint_class,
            "request_method": self.request_method,
            "operation_class": self.operation_class,
            "client_authority": self.client_authority,
        }


@dataclasses.dataclass(frozen=True)
class Provenance:
    authority: str
    endpoint_class: str
    operation: str
    response_status: int | None
    exchange_error_code: str | None
    observed_at: str | None

    def __post_init__(self):
        _req_str(self.authority, "provenance.authority")
        _req_str(self.endpoint_class, "provenance.endpoint_class")
        _req_str(self.operation, "provenance.operation")
        object.__setattr__(self, "response_status",
                           _to_int(self.response_status,
                                   "provenance.response_status"))
        object.__setattr__(self, "exchange_error_code",
                           _opt_str(self.exchange_error_code,
                                    "provenance.exchange_error_code"))
        object.__setattr__(self, "observed_at",
                           _opt_str(self.observed_at,
                                    "provenance.observed_at"))

    def to_dict(self):
        return {
            "authority": self.authority,
            "endpoint_class": self.endpoint_class,
            "operation": self.operation,
            "response_status": self.response_status,
            "exchange_error_code": self.exchange_error_code,
            "observed_at": self.observed_at,
        }


@dataclasses.dataclass(frozen=True)
class Authentication:
    status: str
    failure_classification: str
    credential_variables_present: bool
    credentials_loaded: bool
    endpoint_selected_correctly: bool
    signing_authority: str
    signature_accepted: bool | None
    timestamp_accepted: bool | None

    def __post_init__(self):
        _check_closed(self.status, "authentication.status", AUTH_STATUSES)
        _check_closed(self.failure_classification,
                      "authentication.failure_classification",
                      FAILURE_CLASSIFICATIONS)
        if self.status == "VERIFIED" and self.failure_classification != "NONE":
            raise ArtifactError(
                "authentication VERIFIED requires failure NONE")
        if (self.status == "NOT_ATTEMPTED"
                and self.failure_classification != "NONE"):
            raise ArtifactError(
                "authentication NOT_ATTEMPTED requires failure NONE")
        if (self.status not in ("VERIFIED", "NOT_ATTEMPTED")
                and self.failure_classification == "NONE"):
            raise ArtifactError(
                "authentication %s requires a failure classification"
                % self.status)
        _req_bool(self.credential_variables_present,
                  "authentication.credential_variables_present")
        _req_bool(self.credentials_loaded,
                  "authentication.credentials_loaded")
        _req_bool(self.endpoint_selected_correctly,
                  "authentication.endpoint_selected_correctly")
        _req_str(self.signing_authority,
                 "authentication.signing_authority")
        object.__setattr__(self, "signature_accepted",
                           _opt_bool(self.signature_accepted,
                                     "authentication.signature_accepted"))
        object.__setattr__(self, "timestamp_accepted",
                           _opt_bool(self.timestamp_accepted,
                                     "authentication.timestamp_accepted"))

    def to_dict(self):
        return {
            "status": self.status,
            "failure_classification": self.failure_classification,
            "credential_variables_present":
                self.credential_variables_present,
            "credentials_loaded": self.credentials_loaded,
            "endpoint_selected_correctly":
                self.endpoint_selected_correctly,
            "signing_authority": self.signing_authority,
            "signature_accepted": self.signature_accepted,
            "timestamp_accepted": self.timestamp_accepted,
        }


@dataclasses.dataclass(frozen=True)
class AccountEvidence:
    status: str
    account_class: str | None = None
    currency: str | None = None
    available_balance: Decimal | None = None
    equity: Decimal | None = None
    margin_available: Decimal | None = None
    limitations: tuple = ()

    def __post_init__(self):
        _check_closed(self.status, "account.status", EVIDENCE_STATUSES)
        object.__setattr__(self, "account_class",
                           _opt_str(self.account_class,
                                    "account.account_class"))
        object.__setattr__(self, "currency",
                           _opt_str(self.currency, "account.currency"))
        for field in ("available_balance", "equity", "margin_available"):
            object.__setattr__(self, field,
                               _to_decimal(getattr(self, field),
                                           "account." + field))
        object.__setattr__(self, "limitations",
                           _tuple_of_str(self.limitations,
                                         "account.limitations"))

    def to_dict(self):
        return {
            "status": self.status,
            "account_class": self.account_class,
            "currency": self.currency,
            "available_balance": _dec(self.available_balance),
            "equity": _dec(self.equity),
            "margin_available": _dec(self.margin_available),
            "limitations": list(self.limitations),
        }


@dataclasses.dataclass(frozen=True)
class ContractEvidence:
    status: str
    symbol: str
    contract_type: str | None = None
    contract_status: str | None = None
    quote_currency: str | None = None
    settlement_currency: str | None = None
    tick_size: Decimal | None = None
    quantity_precision: int | None = None
    price_precision: int | None = None
    minimum_order_size: Decimal | None = None
    maximum_order_size: Decimal | None = None
    maximum_leverage: Decimal | None = None
    contract_value: Decimal | None = None
    unavailable_fields: tuple = ()

    def __post_init__(self):
        _check_closed(self.status, "contract.status", EVIDENCE_STATUSES)
        _req_str(self.symbol, "contract.symbol")
        for field in ("contract_type", "contract_status",
                      "quote_currency", "settlement_currency"):
            object.__setattr__(self, field,
                               _opt_str(getattr(self, field),
                                        "contract." + field))
        for field in ("tick_size", "minimum_order_size",
                      "maximum_order_size", "maximum_leverage",
                      "contract_value"):
            object.__setattr__(self, field,
                               _to_decimal(getattr(self, field),
                                           "contract." + field))
        for field in ("quantity_precision", "price_precision"):
            object.__setattr__(self, field,
                               _to_int(getattr(self, field),
                                       "contract." + field))
        object.__setattr__(self, "unavailable_fields",
                           _tuple_of_str(self.unavailable_fields,
                                         "contract.unavailable_fields"))

    def to_dict(self):
        return {
            "status": self.status,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "contract_status": self.contract_status,
            "quote_currency": self.quote_currency,
            "settlement_currency": self.settlement_currency,
            "tick_size": _dec(self.tick_size),
            "quantity_precision": self.quantity_precision,
            "price_precision": self.price_precision,
            "minimum_order_size": _dec(self.minimum_order_size),
            "maximum_order_size": _dec(self.maximum_order_size),
            "maximum_leverage": _dec(self.maximum_leverage),
            "contract_value": _dec(self.contract_value),
            "unavailable_fields": list(self.unavailable_fields),
        }


@dataclasses.dataclass(frozen=True)
class EconomicsEvidence:
    status: str
    fee_model: str | None = None
    maker_fee: Decimal | None = None
    taker_fee: Decimal | None = None
    funding_model: str | None = None
    funding_available: bool | None = None
    slippage_model: str | None = None
    slippage_verified: bool = False
    cost_formula_verified: bool = False
    unavailable_fields: tuple = ()
    limitations: tuple = ()

    def __post_init__(self):
        _check_closed(self.status, "economics.status", EVIDENCE_STATUSES)
        object.__setattr__(self, "fee_model",
                           _opt_str(self.fee_model, "economics.fee_model"))
        for field in ("maker_fee", "taker_fee"):
            object.__setattr__(self, field,
                               _to_decimal(getattr(self, field),
                                           "economics." + field))
        object.__setattr__(self, "funding_model",
                           _opt_str(self.funding_model,
                                    "economics.funding_model"))
        object.__setattr__(self, "funding_available",
                           _opt_bool(self.funding_available,
                                     "economics.funding_available"))
        object.__setattr__(self, "slippage_model",
                           _opt_str(self.slippage_model,
                                    "economics.slippage_model"))
        _req_bool(self.slippage_verified,
                  "economics.slippage_verified")
        _req_bool(self.cost_formula_verified,
                  "economics.cost_formula_verified")
        object.__setattr__(self, "unavailable_fields",
                           _tuple_of_str(self.unavailable_fields,
                                         "economics.unavailable_fields"))
        object.__setattr__(self, "limitations",
                           _tuple_of_str(self.limitations,
                                         "economics.limitations"))

    def to_dict(self):
        return {
            "status": self.status,
            "fee_model": self.fee_model,
            "maker_fee": _dec(self.maker_fee),
            "taker_fee": _dec(self.taker_fee),
            "funding_model": self.funding_model,
            "funding_available": self.funding_available,
            "slippage_model": self.slippage_model,
            "slippage_verified": self.slippage_verified,
            "cost_formula_verified": self.cost_formula_verified,
            "unavailable_fields": list(self.unavailable_fields),
            "limitations": list(self.limitations),
        }


@dataclasses.dataclass(frozen=True)
class OrderLifecycleEvidence:
    status: str
    attempted: bool = False
    sandbox_confirmed: bool = False
    order_creation_verified: bool = False
    fill_verified: bool = False
    cancel_verified: bool = False
    final_state_verified: bool = False
    cleanup_verified: bool = False
    residual_orders: int | None = None
    residual_positions: int | None = None
    failure_classification: str = "NONE"
    limitations: tuple = ()

    def __post_init__(self):
        _check_closed(self.status, "order_lifecycle.status",
                      EVIDENCE_STATUSES)
        _check_closed(self.failure_classification,
                      "order_lifecycle.failure_classification",
                      FAILURE_CLASSIFICATIONS)
        _req_bool(self.attempted, "order_lifecycle.attempted")
        for field in ("sandbox_confirmed", "order_creation_verified",
                      "fill_verified", "cancel_verified",
                      "final_state_verified", "cleanup_verified"):
            _req_bool(getattr(self, field), "order_lifecycle." + field)
        if not self.attempted and self.status not in (
                "NOT_ATTEMPTED", "BLOCKED"):
            raise ArtifactError(
                "order_lifecycle not attempted requires status "
                "NOT_ATTEMPTED or BLOCKED")
        if self.attempted and self.status == "NOT_ATTEMPTED":
            raise ArtifactError(
                "order_lifecycle attempted requires a status other "
                "than NOT_ATTEMPTED")
        if self.status == "VERIFIED" and not (
                self.order_creation_verified
                and self.final_state_verified
                and self.cleanup_verified):
            raise ArtifactError(
                "order_lifecycle VERIFIED requires creation, final "
                "state and cleanup verification")
        object.__setattr__(self, "residual_orders",
                           _to_int(self.residual_orders,
                                   "order_lifecycle.residual_orders"))
        object.__setattr__(self, "residual_positions",
                           _to_int(self.residual_positions,
                                   "order_lifecycle.residual_positions"))
        if self.status == "VERIFIED" and (
                self.residual_orders not in (0, None)
                or self.residual_positions not in (0, None)):
            raise ArtifactError(
                "order_lifecycle VERIFIED requires zero residuals")
        object.__setattr__(self, "limitations",
                           _tuple_of_str(self.limitations,
                                         "order_lifecycle.limitations"))

    def to_dict(self):
        return {
            "status": self.status,
            "attempted": self.attempted,
            "sandbox_confirmed": self.sandbox_confirmed,
            "order_creation_verified": self.order_creation_verified,
            "fill_verified": self.fill_verified,
            "cancel_verified": self.cancel_verified,
            "final_state_verified": self.final_state_verified,
            "cleanup_verified": self.cleanup_verified,
            "residual_orders": self.residual_orders,
            "residual_positions": self.residual_positions,
            "failure_classification": self.failure_classification,
            "limitations": list(self.limitations),
        }


@dataclasses.dataclass(frozen=True)
class Reconciliation:
    status: str
    authorities_compared: tuple = ()
    matched_fields: tuple = ()
    mismatched_fields: tuple = ()
    unavailable_fields: tuple = ()
    local_authority_overridden: bool = False
    notes: tuple = ()

    def __post_init__(self):
        _check_closed(self.status, "reconciliation.status",
                      RECONCILIATION_STATUSES)
        for field in ("authorities_compared", "matched_fields",
                      "mismatched_fields", "unavailable_fields", "notes"):
            object.__setattr__(self, field,
                               _tuple_of_str(getattr(self, field),
                                             "reconciliation." + field))
        if self.local_authority_overridden is not False:
            raise ArtifactError(
                "reconciliation local_authority_overridden must be "
                "False (external evidence never overrides local "
                "authority)")

    def to_dict(self):
        return {
            "status": self.status,
            "authorities_compared": list(self.authorities_compared),
            "matched_fields": list(self.matched_fields),
            "mismatched_fields": list(self.mismatched_fields),
            "unavailable_fields": list(self.unavailable_fields),
            "local_authority_overridden": False,
            "notes": list(self.notes),
        }


@dataclasses.dataclass(frozen=True)
class Limitation:
    code: str
    category: str
    description: str
    blocking: bool

    def __post_init__(self):
        _req_str(self.code, "limitation.code")
        _check_closed(self.category, "limitation.category",
                      LIMITATION_CATEGORIES)
        _req_str(self.description, "limitation.description")
        _req_bool(self.blocking, "limitation.blocking")

    def to_dict(self):
        return {
            "code": self.code,
            "category": self.category,
            "description": self.description,
            "blocking": self.blocking,
        }


@dataclasses.dataclass(frozen=True)
class Safety:
    environment_verified_sandbox: bool
    production_endpoint_used: bool = False
    production_write_attempted: bool = False
    production_order_submitted: bool = False
    production_cancel_attempted: bool = False
    production_account_mutated: bool = False
    live_executor_reached: bool = False
    production_directive_emitted: bool = False
    is_production_ready: bool = False

    def __post_init__(self):
        for field in ("environment_verified_sandbox",
                      "production_endpoint_used",
                      "production_write_attempted",
                      "production_order_submitted",
                      "production_cancel_attempted",
                      "production_account_mutated",
                      "live_executor_reached",
                      "production_directive_emitted"):
            _req_bool(getattr(self, field), "safety." + field)
        if self.is_production_ready is not False:
            raise ArtifactError(
                "safety is_production_ready must be False "
                "(sandbox evidence can never promote production)")

    def to_dict(self):
        return {
            "environment_verified_sandbox":
                self.environment_verified_sandbox,
            "production_endpoint_used": self.production_endpoint_used,
            "production_write_attempted":
                self.production_write_attempted,
            "production_order_submitted":
                self.production_order_submitted,
            "production_cancel_attempted":
                self.production_cancel_attempted,
            "production_account_mutated":
                self.production_account_mutated,
            "live_executor_reached": self.live_executor_reached,
            "production_directive_emitted":
                self.production_directive_emitted,
            "is_production_ready": False,
        }


def _dec(value):
    """Deterministic Decimal serialization: Decimal -> plain string."""
    if value is None:
        return None
    return str(value)


# -------------------------------------------------
# Secret-safety gate (pre-serialization refusal)
# -------------------------------------------------

def assert_no_secrets(payload, forbidden_values=()):
    """Refuse the artifact before serialization on any leak signal.

    * Any mapping KEY exactly matching a forbidden credential field
      name (case-insensitive) is rejected.
    * Any string VALUE shaped as a credential assignment
      (``api_key=...`` / ``"api_secret": "..."`` / ``access-token:
      ...`` ...) is rejected -- naming a public variable in prose
      is allowed, giving it a value is not.
    * Any string VALUE exactly equal to a caller-declared secret
      value is rejected (tests prove the mechanism with dummy
      values; production callers never place secret values near
      the builder -- only booleans).
    """
    secrets = tuple(v for v in (forbidden_values or ())
                    if isinstance(v, str) and v)
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            items = node.items()
        elif isinstance(node, (list, tuple)):
            items = enumerate(node)
        else:
            _check_value(node, secrets)
            continue
        for key, value in items:
            if isinstance(key, str) and key.lower() in FORBIDDEN_FIELD_NAMES:
                raise SecretLeakError(
                    "ARTIFACT_REJECTED_SECRET_LEAK: forbidden field %r"
                    % key)
            _check_value(value, secrets)
            if isinstance(value, (dict, list, tuple)):
                stack.append(value)


def _check_value(value, secrets):
    if not isinstance(value, str) or not value:
        return
    match = _credential_assignment_re().search(value)
    # Placeholder ellipses document the rejected shape without
    # carrying a value; anything concrete is refused.
    if match and match.group(1).strip("\"'") not in ("...", "…"):
        raise SecretLeakError(
            "ARTIFACT_REJECTED_SECRET_LEAK: credential assignment "
            "in artifact string")
    for secret in secrets:
        if value == secret:
            raise SecretLeakError(
                "ARTIFACT_REJECTED_SECRET_LEAK: raw secret value in "
                "artifact string")


# -------------------------------------------------
# Top-level artifact
# -------------------------------------------------

@dataclasses.dataclass(frozen=True)
class SandboxExternalEvidenceArtifact:
    schema_version: str
    artifact_type: str
    artifact_id: str
    identity_algorithm: str
    environment: str
    venue: str
    observation_context: ObservationContext
    provenance: Provenance
    authentication: Authentication
    account: AccountEvidence
    contracts: tuple
    economics: EconomicsEvidence
    order_lifecycle: OrderLifecycleEvidence
    reconciliation: Reconciliation
    limitations: tuple
    safety: Safety
    final_classification: str
    forbidden_values: tuple = ()

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ArtifactError("schema_version must be %r"
                                % SCHEMA_VERSION)
        if self.artifact_type != ARTIFACT_TYPE:
            raise ArtifactError("artifact_type must be %r" % ARTIFACT_TYPE)
        if self.identity_algorithm != IDENTITY_ALGORITHM:
            raise ArtifactError("identity_algorithm must be %r"
                                % IDENTITY_ALGORITHM)
        # Rule: production can never be represented as a sandbox
        # artifact. Venue is pinned to DELTA for this gate.
        if self.environment != ENVIRONMENT:
            raise ArtifactError("environment must be %r" % ENVIRONMENT)
        if self.venue != VENUE:
            raise ArtifactError("venue must be %r" % VENUE)
        for name, kind in (
                ("observation_context", ObservationContext),
                ("provenance", Provenance),
                ("authentication", Authentication),
                ("account", AccountEvidence),
                ("economics", EconomicsEvidence),
                ("order_lifecycle", OrderLifecycleEvidence),
                ("reconciliation", Reconciliation),
                ("safety", Safety)):
            if not isinstance(getattr(self, name), kind):
                raise ArtifactError("%s must be %s, got %s"
                                    % (name, kind.__name__,
                                       type(getattr(self, name)).__name__))
        contracts = self.contracts
        if not isinstance(contracts, (tuple, list)):
            raise ArtifactError("contracts must be a tuple/list")
        contracts = tuple(contracts)
        object.__setattr__(self, "contracts", contracts)
        for item in contracts:
            if not isinstance(item, ContractEvidence):
                raise ArtifactError(
                    "contracts items must be ContractEvidence, got %s"
                    % type(item).__name__)
        limitations = self.limitations
        if not isinstance(limitations, (tuple, list)):
            raise ArtifactError("limitations must be a tuple/list")
        limitations = tuple(limitations)
        object.__setattr__(self, "limitations", limitations)
        for item in limitations:
            if not isinstance(item, Limitation):
                raise ArtifactError(
                    "limitations items must be Limitation, got %s"
                    % type(item).__name__)
        object.__setattr__(self, "forbidden_values",
                           tuple(self.forbidden_values or ()))
        _check_closed(self.final_classification,
                      "final_classification", FINAL_CLASSIFICATIONS)
        # Consistency rules: classification dimensions stay separate.
        auth_status = self.authentication.status
        if self.final_classification == FINAL_VERIFIED:
            if auth_status != "VERIFIED":
                raise ArtifactError(
                    "final VERIFIED requires authentication VERIFIED")
            if self.reconciliation.status == "MISMATCH":
                raise ArtifactError(
                    "final VERIFIED forbids reconciliation MISMATCH")
            if not self.safety.environment_verified_sandbox:
                raise ArtifactError(
                    "final VERIFIED requires sandbox verification")
            if self.safety.production_endpoint_used:
                raise ArtifactError(
                    "final VERIFIED forbids production endpoint use")
        if self.final_classification == FINAL_PARTIAL:
            if auth_status != "VERIFIED":
                raise ArtifactError(
                    "final PARTIAL requires authentication VERIFIED")
        # Secret gate runs on the canonical payload (pre-serialization).
        assert_no_secrets(self.to_dict(include_identity=True),
                          self.forbidden_values)
        # Identity determinism: the supplied id must equal the
        # recomputed stable hash of the identity payload.
        expected = content_hash(self._identity_payload())
        if self.artifact_id != expected:
            raise ArtifactError(
                "artifact_id does not match the deterministic identity "
                "payload (expected %s)" % expected)

    # -------------------------------------------------
    # Construction (single sanctioned path)
    # -------------------------------------------------

    @classmethod
    def create(cls, *, observation_context, provenance,
               authentication, account, contracts, economics,
               order_lifecycle, reconciliation, limitations, safety,
               final_classification, forbidden_values=()):
        """Build an artifact, deriving the deterministic artifact_id."""
        artifact_id = content_hash(cls._identity_payload_for(
            observation_context=observation_context,
            provenance=provenance,
            authentication=authentication,
            account=account,
            contracts=contracts,
            economics=economics,
            order_lifecycle=order_lifecycle,
            reconciliation=reconciliation,
            limitations=limitations,
            safety=safety,
            final_classification=final_classification))
        return cls(
            schema_version=SCHEMA_VERSION,
            artifact_type=ARTIFACT_TYPE,
            artifact_id=artifact_id,
            identity_algorithm=IDENTITY_ALGORITHM,
            environment=ENVIRONMENT,
            venue=VENUE,
            observation_context=observation_context,
            provenance=provenance,
            authentication=authentication,
            account=account,
            contracts=tuple(contracts),
            economics=economics,
            order_lifecycle=order_lifecycle,
            reconciliation=reconciliation,
            limitations=tuple(limitations),
            safety=safety,
            final_classification=final_classification,
            forbidden_values=tuple(forbidden_values or ()),
        )

    # -------------------------------------------------
    # Canonical serialization (fixed field order)
    # -------------------------------------------------

    @staticmethod
    def _identity_payload_for(*, observation_context, provenance,
                              authentication, account, contracts,
                              economics, order_lifecycle,
                              reconciliation, limitations, safety,
                              final_classification):
        """Hash-covered subset: schema literals + evidence content.

        Excludes ``artifact_id`` / ``identity_algorithm`` (derived,
        not inputs) and ``provenance.observed_at`` (observation
        metadata, never identity). Tuples render as lists so the
        hashed form matches the serialized form.
        """
        prov = provenance.to_dict()
        prov = {k: v for k, v in prov.items() if k != "observed_at"}
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": ARTIFACT_TYPE,
            "environment": ENVIRONMENT,
            "venue": VENUE,
            "observation_context": observation_context.to_dict(),
            "provenance": prov,
            "authentication": authentication.to_dict(),
            "account": account.to_dict(),
            "contracts": [c.to_dict() for c in tuple(contracts)],
            "economics": economics.to_dict(),
            "order_lifecycle": order_lifecycle.to_dict(),
            "reconciliation": reconciliation.to_dict(),
            "limitations": [l.to_dict() for l in tuple(limitations)],
            "safety": safety.to_dict(),
            "final_classification": final_classification,
        }

    def _identity_payload(self):
        return self._identity_payload_for(
            observation_context=self.observation_context,
            provenance=self.provenance,
            authentication=self.authentication,
            account=self.account,
            contracts=self.contracts,
            economics=self.economics,
            order_lifecycle=self.order_lifecycle,
            reconciliation=self.reconciliation,
            limitations=self.limitations,
            safety=self.safety,
            final_classification=self.final_classification)

    def to_dict(self, include_identity=True):
        body = self._identity_payload_for(
            observation_context=self.observation_context,
            provenance=self.provenance,
            authentication=self.authentication,
            account=self.account,
            contracts=self.contracts,
            economics=self.economics,
            order_lifecycle=self.order_lifecycle,
            reconciliation=self.reconciliation,
            limitations=self.limitations,
            safety=self.safety,
            final_classification=self.final_classification)
        # Reinsert observation metadata (never hashed) and identity.
        body["provenance"] = self.provenance.to_dict()
        ordered = {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "identity_algorithm": self.identity_algorithm,
            "environment": self.environment,
            "venue": self.venue,
        }
        ordered.update(body)
        if not include_identity:
            for key in ("artifact_id", "identity_algorithm"):
                ordered.pop(key, None)
        return ordered

    def to_json(self):
        """One canonical JSON form (fixed order, compact separators)."""
        return json.dumps(self.to_dict(), separators=(",", ":"),
                          ensure_ascii=True)
