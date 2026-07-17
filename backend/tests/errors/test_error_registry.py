"""Registry sözleşme testleri (Sprint 27.2 T1)."""
import dataclasses

import pytest

from app.errors import (
    DESCRIPTORS, ErrorCategory, ErrorCode, ErrorDescriptor,
    UnknownErrorCodeError, category_of, codes_for_category, describe,
)


def test_every_error_code_has_a_descriptor():
    assert set(DESCRIPTORS.keys()) == set(ErrorCode)


def test_registry_has_no_keys_outside_error_code():
    for key in DESCRIPTORS:
        assert isinstance(key, ErrorCode)


def test_descriptor_is_frozen():
    d = describe(ErrorCode.MISSING_COLUMN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.category = ErrorCategory.INPUT


def test_descriptor_carries_only_code_and_category():
    # Spec §4.3 — retryable/severity bilinçli olarak YOK.
    assert {f.name for f in ErrorDescriptor.__dataclass_fields__.values()} == {
        "code", "category"}


def test_registry_mapping_is_read_only():
    with pytest.raises(TypeError):
        DESCRIPTORS[ErrorCode.MISSING_COLUMN] = None


@pytest.mark.parametrize("code,category", [
    (ErrorCode.INPUT_ERROR, ErrorCategory.INPUT),
    (ErrorCode.EXCEL_PARSE_ERROR, ErrorCategory.INPUT),
    (ErrorCode.SCHEMA_PRUNING_FAILED, ErrorCategory.RETRIEVAL),
    (ErrorCode.SCHEMA_PRUNING_CRASHED, ErrorCategory.RETRIEVAL),
    (ErrorCode.SCHEMA_CONTEXT_SELECTION_CRASHED, ErrorCategory.RETRIEVAL),
    (ErrorCode.LLM_API_ERROR, ErrorCategory.GENERATION),
    (ErrorCode.SQL_GENERATION_EXHAUSTED, ErrorCategory.GENERATION),
    (ErrorCode.MISSING_COLUMN, ErrorCategory.VALIDATION),
    (ErrorCode.SEMANTIC_VALIDATION_FAILED, ErrorCategory.VALIDATION),
    (ErrorCode.UNSAFE_DANGEROUS_FUNCTION, ErrorCategory.SECURITY),
    (ErrorCode.UNSAFE_DML_KEYWORD, ErrorCategory.SECURITY),
    (ErrorCode.UNSAFE_SANDBOX_REJECTED, ErrorCategory.SECURITY),
    (ErrorCode.NON_SELECT_STATEMENT, ErrorCategory.SECURITY),
    (ErrorCode.QUERY_TIMEOUT, ErrorCategory.EXECUTION),
    (ErrorCode.EXECUTION_FAILED, ErrorCategory.EXECUTION),
])
def test_category_of_known_codes(code, category):
    assert category_of(code) is category
    assert describe(code) == ErrorDescriptor(code=code, category=category)


def test_codes_for_category_returns_all_members_of_that_category():
    security = codes_for_category(ErrorCategory.SECURITY)
    assert security == frozenset({
        ErrorCode.MULTIPLE_STATEMENTS, ErrorCode.NON_SELECT_STATEMENT,
        ErrorCode.UNSAFE_DANGEROUS_FUNCTION, ErrorCode.UNSAFE_DML_KEYWORD,
        ErrorCode.UNSAFE_SANDBOX_REJECTED,
    })


def test_codes_for_category_partitions_the_enum():
    seen = set()
    for category in ErrorCategory:
        codes = codes_for_category(category)
        assert not (seen & codes), "bir kod iki kategoride olamaz"
        seen |= codes
    assert seen == set(ErrorCode)


def test_describe_rejects_unknown_code():
    with pytest.raises(UnknownErrorCodeError):
        describe("kesinlikle_boyle_bir_kod_yok")


def test_describe_accepts_plain_string_of_a_known_code():
    assert describe("missing_column").category is ErrorCategory.VALIDATION
