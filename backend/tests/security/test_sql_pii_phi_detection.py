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
