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


from app.security.audit_event import AuditActor, AuditResource


def test_actor_minimal_valid():
    a = AuditActor(subject="user-42")
    assert a.subject == "user-42"
    assert a.tenant is None and a.request_id is None


def test_actor_requires_non_empty_subject():
    with pytest.raises(AuditEventContractError):
        AuditActor(subject="   ")


def test_actor_optional_fields_must_be_str_or_none():
    with pytest.raises(AuditEventContractError):
        AuditActor(subject="u", tenant=123)


def test_actor_to_dict_is_json_safe():
    a = AuditActor(subject="u", tenant="t1", workspace="w1",
                   source_ip="10.0.0.1", request_id="req-1")
    d = a.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d == {"subject": "u", "tenant": "t1", "workspace": "w1",
                 "source_ip": "10.0.0.1", "request_id": "req-1"}


def test_actor_is_frozen():
    a = AuditActor(subject="u")
    with pytest.raises(FrozenInstanceError):
        a.subject = "x"


def test_resource_all_optional():
    r = AuditResource()
    assert r.to_dict() == {"type": None, "id": None, "dialect": None}


def test_resource_to_dict_roundtrips():
    r = AuditResource(type="table", id="users", dialect="postgres")
    assert r.to_dict() == {"type": "table", "id": "users", "dialect": "postgres"}


def test_resource_fields_must_be_str_or_none():
    with pytest.raises(AuditEventContractError):
        AuditResource(type=5)
