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


# Task 4: SQLPiiPhiDetectionRequest
from app.security.sql_pii_phi_detection import SQLPiiPhiDetectionRequest


def test_request_defaults():
    req = SQLPiiPhiDetectionRequest(version=SQL_PII_PHI_DETECTION_CONTRACT_VERSION)
    assert req.sql is None
    assert req.referenced_tables is None
    assert req.referenced_columns is None
    assert req.dialect == "generic"


def test_request_rejects_bad_version():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        SQLPiiPhiDetectionRequest(version="nope")


def test_request_rejects_empty_dialect():
    with pytest.raises(SQLPiiPhiDetectionContractError):
        SQLPiiPhiDetectionRequest(
            version=SQL_PII_PHI_DETECTION_CONTRACT_VERSION, dialect="  ")


def test_request_is_frozen():
    req = SQLPiiPhiDetectionRequest(version=SQL_PII_PHI_DETECTION_CONTRACT_VERSION)
    with pytest.raises(FrozenInstanceError):
        req.sql = "SELECT 1"


# Task 5: _extract_identifiers + _detect_name_matches
from app.security.sql_pii_phi_detection import (
    _extract_identifiers, _detect_name_matches,
)
from app.security._sql_text import to_executable_core


def test_extract_identifiers_includes_unqualified_columns():
    core = to_executable_core("SELECT ssn, email FROM users")
    ids = _extract_identifiers(core)
    assert {"ssn", "email", "users"}.issubset(ids)


def test_extract_identifiers_includes_qualified_tokens():
    core = to_executable_core("SELECT u.ssn FROM public.users u")
    ids = _extract_identifiers(core)
    assert "u.ssn" in ids
    assert "public.users" in ids


def test_name_matches_detect_email_and_ssn():
    found = dict(_detect_name_matches({"users.email", "ssn", "orders"}))
    assert found[SQLPiiPhiCategory.EMAIL] == "users.email"
    assert found[SQLPiiPhiCategory.SSN] == "ssn"
    assert SQLPiiPhiCategory.POSTAL_ADDRESS not in found


def test_name_matches_detect_phi_categories():
    cats = {c for c, _ in _detect_name_matches(
        {"patients.mrn", "visit.diagnosis", "patient"})}
    assert SQLPiiPhiCategory.MEDICAL_RECORD_NUMBER in cats
    assert SQLPiiPhiCategory.DIAGNOSIS in cats
    assert SQLPiiPhiCategory.HEALTH_GENERIC in cats


def test_name_matches_each_pii_category_name():
    samples = {
        "phone": SQLPiiPhiCategory.PHONE,
        "card_number": SQLPiiPhiCategory.CREDIT_CARD,
        "iban": SQLPiiPhiCategory.IBAN,
        "date_of_birth": SQLPiiPhiCategory.DATE_OF_BIRTH,
        "last_name": SQLPiiPhiCategory.PERSON_NAME,
        "street": SQLPiiPhiCategory.POSTAL_ADDRESS,
    }
    for ident, expected in samples.items():
        cats = {c for c, _ in _detect_name_matches({ident})}
        assert expected in cats, ident


def test_name_matches_are_deterministically_ordered():
    a = _detect_name_matches({"users.ssn", "users.email", "patient"})
    b = _detect_name_matches({"patient", "users.email", "users.ssn"})
    assert a == b


def test_name_matches_empty_for_benign_identifiers():
    assert _detect_name_matches({"orders", "id", "total", "qty"}) == []


# Task 6: _luhn_ok + _detect_literal_matches
from app.security.sql_pii_phi_detection import _luhn_ok, _detect_literal_matches


def test_luhn_accepts_valid_card_and_rejects_invalid():
    assert _luhn_ok("4111111111111111") is True
    assert _luhn_ok("4111111111111112") is False
    assert _luhn_ok("123") is False           # too short
    assert _luhn_ok("notanumber") is False


def test_literal_detects_email_ssn_iban():
    cats = {c for c, _ in _detect_literal_matches(
        "... WHERE email = 'a.b@example.com' AND ssn = '123-45-6789' "
        "AND acct = 'GB82WEST12345698765432'")}
    assert SQLPiiPhiCategory.EMAIL in cats
    assert SQLPiiPhiCategory.SSN in cats
    assert SQLPiiPhiCategory.IBAN in cats


def test_literal_detects_luhn_card_high_confidence():
    found = _detect_literal_matches("INSERT INTO t(cc) VALUES ('4111111111111111')")
    card = [conf for cat, conf in found if cat == SQLPiiPhiCategory.CREDIT_CARD]
    assert card == [SQLPiiPhiConfidence.HIGH]


def test_literal_does_not_flag_non_luhn_digit_run_as_card():
    found = _detect_literal_matches("WHERE order_no = '4111111111111112'")
    cats = {c for c, _ in found}
    assert SQLPiiPhiCategory.CREDIT_CARD not in cats


def test_literal_empty_for_benign_sql():
    assert _detect_literal_matches("SELECT id, qty FROM orders WHERE qty > 3") == []
