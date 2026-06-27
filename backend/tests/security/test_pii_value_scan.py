from app.security._pii_value_scan import (
    SQLDataClass,
    SQLPiiPhiCategory,
    SQLPiiPhiConfidence,
    _CATEGORY_DATA_CLASS,
    _CONFIDENCE_ORDER,
    _luhn_ok,
    scan_value_categories,
)


def test_enums_have_expected_members():
    assert SQLDataClass.PII.value == "pii"
    assert SQLDataClass.PHI.value == "phi"
    assert SQLPiiPhiCategory.EMAIL.value == "email"
    assert {c.value for c in SQLPiiPhiConfidence} == {"low", "medium", "high"}


def test_category_data_class_maps_phi_categories():
    assert _CATEGORY_DATA_CLASS[SQLPiiPhiCategory.EMAIL] == SQLDataClass.PII
    assert _CATEGORY_DATA_CLASS[SQLPiiPhiCategory.DIAGNOSIS] == SQLDataClass.PHI
    assert _CATEGORY_DATA_CLASS[SQLPiiPhiCategory.MEDICAL_RECORD_NUMBER] == SQLDataClass.PHI


def test_confidence_order_is_total():
    assert _CONFIDENCE_ORDER[SQLPiiPhiConfidence.LOW] < _CONFIDENCE_ORDER[SQLPiiPhiConfidence.MEDIUM]
    assert _CONFIDENCE_ORDER[SQLPiiPhiConfidence.MEDIUM] < _CONFIDENCE_ORDER[SQLPiiPhiConfidence.HIGH]


def test_luhn_accepts_valid_card_and_rejects_invalid():
    assert _luhn_ok("4111111111111111") is True
    assert _luhn_ok("4111111111111112") is False
    assert _luhn_ok("123") is False
    assert _luhn_ok("notanumber") is False


def test_scan_detects_email_ssn_iban():
    cats = {c for c, _ in scan_value_categories(
        "email a.b@example.com ssn 123-45-6789 acct GB82WEST12345698765432")}
    assert SQLPiiPhiCategory.EMAIL in cats
    assert SQLPiiPhiCategory.SSN in cats
    assert SQLPiiPhiCategory.IBAN in cats


def test_scan_credit_card_is_high_confidence():
    out = scan_value_categories("card 4111 1111 1111 1111")
    assert (SQLPiiPhiCategory.CREDIT_CARD, SQLPiiPhiConfidence.HIGH) in out


def test_scan_clean_value_returns_empty():
    assert scan_value_categories("just some text 42") == []
