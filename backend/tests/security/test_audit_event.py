import json
import hashlib
import pytest
from dataclasses import FrozenInstanceError

from app.security.audit_event import (
    AUDIT_EVENT_CONTRACT_VERSION,
    AuditEventContractError,
    AuditCategory,
    AuditOutcome,
    AuditSeverity,
    _SEVERITY_ORDER,
)


def test_contract_version_is_v1():
    assert AUDIT_EVENT_CONTRACT_VERSION == "audit_event_contract_v1"


def test_error_is_value_error():
    assert issubclass(AuditEventContractError, ValueError)


def test_categories_cover_all_six_sources():
    assert {c.value for c in AuditCategory} == {
        "authz_permission", "tenant_boundary", "read_only",
        "query_risk", "sensitive_data", "pii_phi",
    }


def test_outcomes():
    assert {o.value for o in AuditOutcome} == {
        "allowed", "denied", "requires_approval", "flagged", "error",
    }


def test_severity_order_is_strictly_increasing():
    assert (
        _SEVERITY_ORDER[AuditSeverity.INFO]
        < _SEVERITY_ORDER[AuditSeverity.LOW]
        < _SEVERITY_ORDER[AuditSeverity.MEDIUM]
        < _SEVERITY_ORDER[AuditSeverity.HIGH]
        < _SEVERITY_ORDER[AuditSeverity.CRITICAL]
    )
