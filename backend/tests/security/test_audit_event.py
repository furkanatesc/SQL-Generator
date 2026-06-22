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


from app.security.audit_event import AuditEvent

# A valid 64-hex string for direct construction tests (chain math is Task 4).
_H = "a" * 64


def _make_event(**overrides):
    fields = dict(
        schema_version=AUDIT_EVENT_CONTRACT_VERSION,
        event_id="11111111-1111-1111-1111-111111111111",
        occurred_at="2026-06-21T12:00:00Z",
        category=AuditCategory.READ_ONLY,
        action="enforce_read_only",
        outcome=AuditOutcome.ALLOWED,
        severity=AuditSeverity.INFO,
        actor=AuditActor(subject="user-1", tenant="t1"),
        resource=AuditResource(type="query", id="q1", dialect="generic"),
        reason_code="read_only_ok",
        reason="statement is read-only",
        contract_source="sql_read_only_enforcement_contract_v1",
        sql_sha256="b" * 64,
        details={"decision": "allow"},
        prev_hash=None,
        entry_hash=_H,
    )
    fields.update(overrides)
    return AuditEvent(**fields)


def test_event_builds_and_to_dict_roundtrips():
    e = _make_event()
    d = e.to_dict()
    assert json.loads(json.dumps(d)) == d          # JSON-safe
    assert d["category"] == "read_only"            # enum -> value
    assert d["outcome"] == "allowed"
    assert d["severity"] == "info"
    assert d["actor"]["subject"] == "user-1"
    assert d["entry_hash"] == _H


def test_payload_excludes_entry_hash_includes_prev_hash():
    e = _make_event(prev_hash=_H)
    payload = e._payload()
    assert "entry_hash" not in payload
    assert payload["prev_hash"] == _H


def test_event_rejects_wrong_schema_version():
    with pytest.raises(AuditEventContractError):
        _make_event(schema_version="audit_event_contract_v2")


def test_event_rejects_empty_required_strings():
    for field in ("event_id", "occurred_at", "action", "reason_code",
                  "reason", "contract_source"):
        with pytest.raises(AuditEventContractError):
            _make_event(**{field: "  "})


def test_event_rejects_bad_enum_types():
    with pytest.raises(AuditEventContractError):
        _make_event(category="read_only")          # bare string, not enum
    with pytest.raises(AuditEventContractError):
        _make_event(outcome="allowed")
    with pytest.raises(AuditEventContractError):
        _make_event(severity="info")


def test_event_rejects_bad_actor_resource():
    with pytest.raises(AuditEventContractError):
        _make_event(actor={"subject": "u"})        # not an AuditActor
    with pytest.raises(AuditEventContractError):
        _make_event(resource="users")              # not an AuditResource


def test_event_rejects_bad_hashes():
    with pytest.raises(AuditEventContractError):
        _make_event(entry_hash="xyz")              # not 64-hex
    with pytest.raises(AuditEventContractError):
        _make_event(sql_sha256="nope")
    with pytest.raises(AuditEventContractError):
        _make_event(prev_hash="zz")


def test_event_sql_sha256_and_prev_hash_may_be_none():
    e = _make_event(sql_sha256=None, prev_hash=None)
    assert e.sql_sha256 is None and e.prev_hash is None


def test_event_details_must_be_dict():
    with pytest.raises(AuditEventContractError):
        _make_event(details=["not", "a", "dict"])


def test_event_is_frozen():
    e = _make_event()
    with pytest.raises(FrozenInstanceError):
        e.reason = "x"


def test_event_to_dict_is_secret_free():
    # Planting a raw SQL string anywhere user-controlled must not surface it;
    # the record never has a raw-SQL field. details is the source's own dict.
    e = _make_event(details={"decision": "allow", "sql_sha256": "b" * 64})
    blob = json.dumps(e.to_dict())
    assert "SELECT" not in blob.upper()
    assert "users.ssn" not in blob.lower()


from app.security.audit_event import compute_entry_hash, link, verify_chain


def _link_kwargs(**overrides):
    kw = dict(
        event_id="e1",
        occurred_at="2026-06-21T12:00:00Z",
        category=AuditCategory.READ_ONLY,
        action="enforce_read_only",
        outcome=AuditOutcome.ALLOWED,
        severity=AuditSeverity.INFO,
        actor=AuditActor(subject="u"),
        resource=AuditResource(type="query", id="q1"),
        reason_code="read_only_ok",
        reason="ok",
        contract_source="sql_read_only_enforcement_contract_v1",
        sql_sha256=None,
        details={"decision": "allow"},
    )
    kw.update(overrides)
    return kw


def test_link_genesis_has_none_prev_hash():
    e = link(None, **_link_kwargs())
    assert e.prev_hash is None
    assert compute_entry_hash(e) == e.entry_hash


def test_entry_hash_is_deterministic():
    e1 = link(None, **_link_kwargs())
    e2 = link(None, **_link_kwargs())
    assert e1.entry_hash == e2.entry_hash


def test_entry_hash_changes_when_a_field_changes():
    e1 = link(None, **_link_kwargs(reason="ok"))
    e2 = link(None, **_link_kwargs(reason="different"))
    assert e1.entry_hash != e2.entry_hash


def test_chain_links_prev_to_entry():
    e0 = link(None, **_link_kwargs(event_id="e0"))
    e1 = link(e0, **_link_kwargs(event_id="e1"))
    e2 = link(e1, **_link_kwargs(event_id="e2"))
    assert e1.prev_hash == e0.entry_hash
    assert e2.prev_hash == e1.entry_hash
    assert verify_chain([e0, e1, e2]) is None


def test_verify_chain_empty_and_single():
    assert verify_chain([]) is None
    assert verify_chain([link(None, **_link_kwargs())]) is None


def test_verify_chain_detects_mutation():
    e0 = link(None, **_link_kwargs(event_id="e0"))
    e1 = link(e0, **_link_kwargs(event_id="e1"))
    e2 = link(e1, **_link_kwargs(event_id="e2"))
    # Tamper: replace e1 with a copy whose reason differs but keeps old hashes.
    import dataclasses
    tampered = dataclasses.replace(e1, reason="tampered")  # entry_hash now stale
    assert verify_chain([e0, tampered, e2]) == 1


def test_verify_chain_detects_reorder():
    e0 = link(None, **_link_kwargs(event_id="e0"))
    e1 = link(e0, **_link_kwargs(event_id="e1"))
    assert verify_chain([e1, e0]) == 0   # e1 first: prev_hash != None -> broken at 0


def test_verify_chain_detects_deletion():
    e0 = link(None, **_link_kwargs(event_id="e0"))
    e1 = link(e0, **_link_kwargs(event_id="e1"))
    e2 = link(e1, **_link_kwargs(event_id="e2"))
    # Drop e1: e2.prev_hash no longer matches e0.entry_hash.
    assert verify_chain([e0, e2]) == 1
