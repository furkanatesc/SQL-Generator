import json
import pytest
from dataclasses import FrozenInstanceError

from app.security.sql_pii_phi_detection import (
    SQL_PII_PHI_DETECTION_CONTRACT_VERSION,
    SQLPiiPhiDetectionContractError,
    SQLDataClass,
    SQLPiiPhiCategory,
    SQLPiiPhiDetectionSource,
    SQLPiiPhiConfidence,
    SQLPiiPhiReasonCode,
    SQLPiiPhiEvaluatedVia,
    SQLPiiPhiDeclaration,
    _CATEGORY_DATA_CLASS,
    _CONFIDENCE_ORDER,
    _normalize_id,
)


def test_contract_version_is_v1():
    assert SQL_PII_PHI_DETECTION_CONTRACT_VERSION == "sql_pii_phi_detection_contract_v1"


def test_error_is_value_error():
    assert issubclass(SQLPiiPhiDetectionContractError, ValueError)


def test_every_category_maps_to_a_data_class():
    for cat in SQLPiiPhiCategory:
        assert _CATEGORY_DATA_CLASS[cat] in (SQLDataClass.PII, SQLDataClass.PHI)


def test_phi_categories_are_phi():
    for cat in (
        SQLPiiPhiCategory.MEDICAL_RECORD_NUMBER,
        SQLPiiPhiCategory.DIAGNOSIS,
        SQLPiiPhiCategory.HEALTH_GENERIC,
    ):
        assert _CATEGORY_DATA_CLASS[cat] == SQLDataClass.PHI


def test_confidence_order_is_strictly_increasing():
    assert (
        _CONFIDENCE_ORDER[SQLPiiPhiConfidence.LOW]
        < _CONFIDENCE_ORDER[SQLPiiPhiConfidence.MEDIUM]
        < _CONFIDENCE_ORDER[SQLPiiPhiConfidence.HIGH]
    )


def test_normalize_id_lowercases_and_strips():
    assert _normalize_id("  Users.SSN ") == "users.ssn"


def test_declaration_normalizes_resource_id():
    d = SQLPiiPhiDeclaration(resource_id="  Users.SSN ", category=SQLPiiPhiCategory.SSN)
    assert d.resource_id == "users.ssn"
    assert d.category == SQLPiiPhiCategory.SSN


def test_declaration_is_frozen():
    d = SQLPiiPhiDeclaration(resource_id="users.ssn", category=SQLPiiPhiCategory.SSN)
    with pytest.raises(FrozenInstanceError):
        d.category = SQLPiiPhiCategory.EMAIL


def test_declaration_rejects_non_enum_category():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        SQLPiiPhiDeclaration(resource_id="users.ssn", category="ssn")


def test_declaration_rejects_empty_resource_id():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        SQLPiiPhiDeclaration(resource_id="   ", category=SQLPiiPhiCategory.SSN)


def test_declaration_rejects_unqualified_resource_id():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        SQLPiiPhiDeclaration(resource_id="ssn", category=SQLPiiPhiCategory.SSN)


# Task 3: SQLPiiPhiMatch + SQLPiiPhiDetectionResult
from app.security.sql_pii_phi_detection import (
    SQLPiiPhiMatch,
    SQLPiiPhiDetectionResult,
)


def _match(identifier="users.ssn"):
    return SQLPiiPhiMatch(
        category=SQLPiiPhiCategory.SSN,
        data_class=SQLDataClass.PII,
        source=SQLPiiPhiDetectionSource.DECLARED,
        confidence=SQLPiiPhiConfidence.HIGH,
        identifier=identifier,
    )


def _result(**kw):
    base = dict(
        version=SQL_PII_PHI_DETECTION_CONTRACT_VERSION,
        detected=(_match(),),
        categories=(SQLPiiPhiCategory.SSN,),
        has_phi=False,
        highest_confidence=SQLPiiPhiConfidence.HIGH,
        reason_code=SQLPiiPhiReasonCode.PII_DETECTED,
        reason="detected",
        sql_sha256="a" * 64,
        evaluated_via=SQLPiiPhiEvaluatedVia.EXPLICIT_REFERENCES,
        dialect="generic",
    )
    base.update(kw)
    return SQLPiiPhiDetectionResult(**base)


def test_match_to_dict_is_json_safe():
    d = _match().to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["category"] == "ssn"
    assert d["data_class"] == "pii"
    assert d["source"] == "declared"
    assert d["confidence"] == "high"
    assert d["identifier"] == "users.ssn"


def test_match_identifier_can_be_none():
    m = SQLPiiPhiMatch(
        category=SQLPiiPhiCategory.CREDIT_CARD, data_class=SQLDataClass.PII,
        source=SQLPiiPhiDetectionSource.LITERAL_VALUE,
        confidence=SQLPiiPhiConfidence.HIGH, identifier=None)
    assert m.to_dict()["identifier"] is None


def test_result_to_dict_is_json_safe_and_secret_free():
    d = _result().to_dict()
    s = json.dumps(d)
    assert json.loads(s) == d
    assert d["categories"] == ["ssn"]
    assert d["has_phi"] is False
    assert d["highest_confidence"] == "high"
    assert d["evaluated_via"] == "explicit_references"
    assert "sql" not in d
    assert "raw_sql" not in d


def test_result_highest_confidence_none_serializes():
    d = _result(highest_confidence=None, detected=(), categories=(),
                reason_code=SQLPiiPhiReasonCode.NO_PII_PHI_DETECTED).to_dict()
    assert d["highest_confidence"] is None


def test_result_is_frozen():
    with pytest.raises(FrozenInstanceError):
        _result().has_phi = True


def test_result_rejects_bad_version():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        _result(version="nope")


def test_result_rejects_bad_sha256():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        _result(sql_sha256="XYZ")


def test_result_allows_none_sha256():
    assert _result(sql_sha256=None).sql_sha256 is None


def test_result_rejects_non_match_in_detected():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        _result(detected=("not-a-match",))


def test_result_rejects_non_bool_has_phi():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        _result(has_phi="yes")
