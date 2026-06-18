"""Sprint 26.0 — SQL Permission Policy Contract (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint does NOT implement
a real enforcement engine, tenant boundary, RBAC, or AuthN — it defines the
*contract* by which the system will, before running any SQL, answer:

* Which permission action is this?
* Is it allowed, denied, or does it need approval?
* Why was that decision made (audit-grade reason code)?
* Is the decision deterministic and free of secrets?

Core security principle — **fail closed**: the policy can NEVER allow on
uncertainty. Unknown action, unknown resource type, missing subject, missing
resource, unconfigured policy, or invalid input all resolve to ``DENY``. "I don't
know, so let it through" is the single most dangerous behavior in a security
layer; this contract does the opposite.

Out of scope (later sprints): tenant/workspace boundary (26.1), read-only
enforcement hardening (26.2), risk classifier (26.3), sensitive table/column
policy (26.4), PII/PHI detection (26.5), audit persistence (26.6), approval
workflow implementation (26.7), credential vault (26.10), API/UI, and any DB or
adapter execution. This module imports no DB driver and performs no I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple, Union

SQL_PERMISSION_POLICY_CONTRACT_VERSION = "sql_permission_policy_contract_v1"


class SQLPermissionPolicyContractError(ValueError):
    """Raised when permission policy contract rules or configurations are violated."""
    pass


class SQLPermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class SQLPermissionAction(str, Enum):
    GENERATE_SQL = "generate_sql"
    VALIDATE_SQL = "validate_sql"
    EXPLAIN_SQL = "explain_sql"
    EXECUTE_SQL = "execute_sql"
    READ_SCHEMA = "read_schema"
    READ_RESULTS = "read_results"


class SQLPermissionResourceType(str, Enum):
    SCHEMA = "schema"
    TABLE = "table"
    COLUMN = "column"
    QUERY = "query"
    CONNECTION = "connection"
    RESULT_SET = "result_set"


class SQLPermissionReasonCode(str, Enum):
    EXPLICIT_ALLOW = "explicit_allow"
    EXPLICIT_DENY = "explicit_deny"
    DEFAULT_DENY = "default_deny"
    UNKNOWN_ACTION = "unknown_action"
    UNKNOWN_RESOURCE = "unknown_resource"
    MISSING_SUBJECT = "missing_subject"
    MISSING_RESOURCE = "missing_resource"
    REQUIRES_APPROVAL = "requires_approval"
    POLICY_NOT_CONFIGURED = "policy_not_configured"


def _resolve_action(value: Any) -> Optional[SQLPermissionAction]:
    """Return the matching :class:`SQLPermissionAction`, or ``None`` if unknown.

    Requests come from outside the trust boundary, so ``action`` may be a raw
    string. Anything that does not map to a known action resolves to ``None`` and
    is then denied (fail closed).
    """
    if isinstance(value, SQLPermissionAction):
        return value
    if isinstance(value, str):
        try:
            return SQLPermissionAction(value)
        except ValueError:
            return None
    return None


def _resolve_resource_type(value: Any) -> Optional[SQLPermissionResourceType]:
    if isinstance(value, SQLPermissionResourceType):
        return value
    if isinstance(value, str):
        try:
            return SQLPermissionResourceType(value)
        except ValueError:
            return None
    return None


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


@dataclass(frozen=True)
class SQLPermissionPolicyRule:
    """A single, trusted, immutable allow/deny/approval rule.

    Rules are internal policy configuration (not untrusted input): ``action`` and
    ``resource_type`` MUST be proper enum members. A rule matches a request when
    action, resource type, and resource id are all equal.
    """
    action: SQLPermissionAction
    resource_type: SQLPermissionResourceType
    resource_id: str
    decision: SQLPermissionDecision
    policy_id: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.action, SQLPermissionAction):
            raise SQLPermissionPolicyContractError("rule.action must be a SQLPermissionAction")
        if not isinstance(self.resource_type, SQLPermissionResourceType):
            raise SQLPermissionPolicyContractError("rule.resource_type must be a SQLPermissionResourceType")
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            raise SQLPermissionPolicyContractError("rule.resource_id must be a non-empty string")
        if not isinstance(self.decision, SQLPermissionDecision):
            raise SQLPermissionPolicyContractError("rule.decision must be a SQLPermissionDecision")
        if self.policy_id is not None and (not isinstance(self.policy_id, str) or not self.policy_id.strip()):
            raise SQLPermissionPolicyContractError("rule.policy_id must be a non-empty string or None")


@dataclass(frozen=True)
class SQLPermissionPolicyRequest:
    """An immutable permission-decision request.

    ``action`` / ``resource_type`` accept either an enum member or a raw string,
    because requests cross the trust boundary; the policy resolves and validates
    them (unknown values are denied, never allowed). ``context`` is auxiliary,
    possibly-sensitive metadata; it is defensively copied and is NEVER echoed into
    the result.
    """
    version: str
    subject_id: str
    action: Union[SQLPermissionAction, str]
    resource_type: Union[SQLPermissionResourceType, str]
    resource_id: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.version != SQL_PERMISSION_POLICY_CONTRACT_VERSION:
            raise SQLPermissionPolicyContractError(f"Invalid request version: {self.version}")
        if not isinstance(self.subject_id, str):
            raise SQLPermissionPolicyContractError("subject_id must be a string")
        if not isinstance(self.action, (SQLPermissionAction, str)) or (isinstance(self.action, str) and not self.action.strip()):
            raise SQLPermissionPolicyContractError("action must be a SQLPermissionAction or non-empty string")
        if not isinstance(self.resource_type, (SQLPermissionResourceType, str)) or (isinstance(self.resource_type, str) and not self.resource_type.strip()):
            raise SQLPermissionPolicyContractError("resource_type must be a SQLPermissionResourceType or non-empty string")
        if not isinstance(self.resource_id, str):
            raise SQLPermissionPolicyContractError("resource_id must be a string")
        if not isinstance(self.context, Mapping):
            raise SQLPermissionPolicyContractError("context must be a mapping")
        # Defensive immutable-ish copy so later external mutation can't change the request.
        object.__setattr__(self, "context", dict(self.context))


@dataclass(frozen=True)
class SQLPermissionPolicyResult:
    """An immutable, audit-grade, secret-free permission decision.

    Deliberately carries NO ``context``: auxiliary request metadata (which may
    hold connection strings, passwords, tokens, raw SQL, or PII) never reaches a
    result. Only the decision, an audit reason code, a short reason string, and
    the echoed action/resource identifiers are exposed.
    """
    version: str
    decision: SQLPermissionDecision
    reason_code: SQLPermissionReasonCode
    reason: str
    subject_id: str
    action: Union[SQLPermissionAction, str]
    resource_type: Union[SQLPermissionResourceType, str]
    resource_id: str
    policy_id: Optional[str] = None

    def __post_init__(self):
        if self.version != SQL_PERMISSION_POLICY_CONTRACT_VERSION:
            raise SQLPermissionPolicyContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.decision, SQLPermissionDecision):
            raise SQLPermissionPolicyContractError("decision must be a SQLPermissionDecision")
        if not isinstance(self.reason_code, SQLPermissionReasonCode):
            raise SQLPermissionPolicyContractError("reason_code must be a SQLPermissionReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SQLPermissionPolicyContractError("reason must be a non-empty string")
        if not isinstance(self.subject_id, str):
            raise SQLPermissionPolicyContractError("subject_id must be a string")
        if not isinstance(self.action, (SQLPermissionAction, str)):
            raise SQLPermissionPolicyContractError("action must be a SQLPermissionAction or string")
        if not isinstance(self.resource_type, (SQLPermissionResourceType, str)):
            raise SQLPermissionPolicyContractError("resource_type must be a SQLPermissionResourceType or string")
        if not isinstance(self.resource_id, str):
            raise SQLPermissionPolicyContractError("resource_id must be a string")
        if self.policy_id is not None and not isinstance(self.policy_id, str):
            raise SQLPermissionPolicyContractError("policy_id must be a string or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "subject_id": self.subject_id,
            "action": _enum_value(self.action),
            "resource_type": _enum_value(self.resource_type),
            "resource_id": self.resource_id,
            "policy_id": self.policy_id,
        }


class SQLPermissionPolicyContract:
    """Deterministic, default-deny SQL permission policy.

    Constructed with an optional immutable ruleset (trusted internal config). With
    no ruleset the policy is "not configured" and denies everything. The decision
    order is fail-closed:

    1. Missing subject            -> DENY / MISSING_SUBJECT
    2. Unknown / unsupported action -> DENY / UNKNOWN_ACTION
    3. Unknown / unsupported resource type -> DENY / UNKNOWN_RESOURCE
    4. Missing resource id        -> DENY / MISSING_RESOURCE
    5. No ruleset configured      -> DENY / POLICY_NOT_CONFIGURED
    6. Matching rules             -> deny-overrides: DENY > REQUIRES_APPROVAL > ALLOW
    7. Ruleset configured, no match -> DENY / DEFAULT_DENY
    """

    def __init__(
        self,
        rules: Optional[Sequence[SQLPermissionPolicyRule]] = None,
        policy_id: Optional[str] = None,
    ):
        resolved: Tuple[SQLPermissionPolicyRule, ...] = tuple(rules) if rules else ()
        for rule in resolved:
            if not isinstance(rule, SQLPermissionPolicyRule):
                raise SQLPermissionPolicyContractError("each rule must be a SQLPermissionPolicyRule")
        if policy_id is not None and (not isinstance(policy_id, str) or not policy_id.strip()):
            raise SQLPermissionPolicyContractError("policy_id must be a non-empty string or None")
        self._rules = resolved
        self._policy_id = policy_id

    @property
    def is_configured(self) -> bool:
        return bool(self._rules)

    def evaluate(self, request: SQLPermissionPolicyRequest) -> SQLPermissionPolicyResult:
        if not isinstance(request, SQLPermissionPolicyRequest):
            raise SQLPermissionPolicyContractError("request must be a SQLPermissionPolicyRequest")

        action = _resolve_action(request.action)
        resource_type = _resolve_resource_type(request.resource_type)

        # 1. Subject must be present (fail closed on missing identity).
        if not request.subject_id.strip():
            return self._deny(request, action, resource_type,
                              SQLPermissionReasonCode.MISSING_SUBJECT,
                              "Request denied: subject_id is missing.")

        # 2. Action must be a recognized permission action.
        if action is None:
            return self._deny(request, action, resource_type,
                              SQLPermissionReasonCode.UNKNOWN_ACTION,
                              f"Request denied: action '{_enum_value(request.action)}' is not a recognized permission action.")

        # 3. Resource type must be a recognized resource type.
        if resource_type is None:
            return self._deny(request, action, resource_type,
                              SQLPermissionReasonCode.UNKNOWN_RESOURCE,
                              f"Request denied: resource type '{_enum_value(request.resource_type)}' is not recognized.")

        # 4. Resource id must be present.
        if not request.resource_id.strip():
            return self._deny(request, action, resource_type,
                              SQLPermissionReasonCode.MISSING_RESOURCE,
                              "Request denied: resource_id is missing.")

        # 5. A policy with no rules is not configured -> deny.
        if not self._rules:
            return self._deny(request, action, resource_type,
                              SQLPermissionReasonCode.POLICY_NOT_CONFIGURED,
                              "Request denied: no permission policy is configured (default deny).")

        # 6. Match rules with deny-overrides precedence.
        matched = [
            rule for rule in self._rules
            if rule.action == action
            and rule.resource_type == resource_type
            and rule.resource_id == request.resource_id
        ]
        deny_rule = next((r for r in matched if r.decision == SQLPermissionDecision.DENY), None)
        if deny_rule is not None:
            return self._result(request, action, resource_type,
                                SQLPermissionDecision.DENY, SQLPermissionReasonCode.EXPLICIT_DENY,
                                "Request denied by an explicit policy rule.", deny_rule.policy_id)
        approval_rule = next((r for r in matched if r.decision == SQLPermissionDecision.REQUIRES_APPROVAL), None)
        if approval_rule is not None:
            return self._result(request, action, resource_type,
                                SQLPermissionDecision.REQUIRES_APPROVAL, SQLPermissionReasonCode.REQUIRES_APPROVAL,
                                "Request requires approval per policy rule.", approval_rule.policy_id)
        allow_rule = next((r for r in matched if r.decision == SQLPermissionDecision.ALLOW), None)
        if allow_rule is not None:
            return self._result(request, action, resource_type,
                                SQLPermissionDecision.ALLOW, SQLPermissionReasonCode.EXPLICIT_ALLOW,
                                "Request allowed by an explicit policy rule.", allow_rule.policy_id)

        # 7. Configured policy, but nothing matched -> default deny.
        return self._deny(request, action, resource_type,
                          SQLPermissionReasonCode.DEFAULT_DENY,
                          "Request denied: no matching policy rule (default deny).")

    def _deny(
        self,
        request: SQLPermissionPolicyRequest,
        action: Optional[SQLPermissionAction],
        resource_type: Optional[SQLPermissionResourceType],
        reason_code: SQLPermissionReasonCode,
        reason: str,
    ) -> SQLPermissionPolicyResult:
        return self._result(request, action, resource_type, SQLPermissionDecision.DENY, reason_code, reason, self._policy_id)

    def _result(
        self,
        request: SQLPermissionPolicyRequest,
        action: Optional[SQLPermissionAction],
        resource_type: Optional[SQLPermissionResourceType],
        decision: SQLPermissionDecision,
        reason_code: SQLPermissionReasonCode,
        reason: str,
        policy_id: Optional[str],
    ) -> SQLPermissionPolicyResult:
        return SQLPermissionPolicyResult(
            version=SQL_PERMISSION_POLICY_CONTRACT_VERSION,
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            subject_id=request.subject_id,
            # Echo the resolved enum when known; otherwise the raw (unknown) value.
            action=action if action is not None else _enum_value(request.action),
            resource_type=resource_type if resource_type is not None else _enum_value(request.resource_type),
            resource_id=request.resource_id,
            policy_id=policy_id,
        )
