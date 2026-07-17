"""Kod -> descriptor registry'si (Sprint 27.2).

ErrorDescriptor bilinçli olarak YALNIZ code + category taşır. retryable ve
severity EKLENMEDİ: bu sprint'te tüketicileri yok ve kullanılmayan alan
sözleşmeleri çürütür. Registry'ye sonradan alan eklemek ucuz ve kırıcı değil;
kod DEĞERLERİNİ sonradan değiştirmek kırıcı — o yüzden değerler şimdi doğru
yapıldı, alanlar ihtiyaç doğunca eklenecek.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.errors.categories import ErrorCategory
from app.errors.codes import ErrorCode


class UnknownErrorCodeError(KeyError):
    """Registry'de olmayan bir kod sorgulandı."""


@dataclass(frozen=True)
class ErrorDescriptor:
    code: ErrorCode
    category: ErrorCategory


_CATEGORY_BY_CODE: dict[ErrorCode, ErrorCategory] = {
    ErrorCode.INPUT_ERROR: ErrorCategory.INPUT,
    ErrorCode.EXCEL_PARSE_ERROR: ErrorCategory.INPUT,

    ErrorCode.SCHEMA_PRUNING_FAILED: ErrorCategory.RETRIEVAL,
    ErrorCode.SCHEMA_PRUNING_CRASHED: ErrorCategory.RETRIEVAL,
    ErrorCode.SCHEMA_CONTEXT_SELECTION_CRASHED: ErrorCategory.RETRIEVAL,

    ErrorCode.LLM_API_ERROR: ErrorCategory.GENERATION,
    ErrorCode.SQL_GENERATION_EXHAUSTED: ErrorCategory.GENERATION,

    ErrorCode.EMPTY_SQL: ErrorCategory.VALIDATION,
    ErrorCode.SQL_PARSE_ERROR: ErrorCategory.VALIDATION,
    ErrorCode.SYNTAX_ERROR: ErrorCategory.VALIDATION,
    ErrorCode.MISSING_TABLE: ErrorCategory.VALIDATION,
    ErrorCode.MISSING_COLUMN: ErrorCategory.VALIDATION,
    ErrorCode.SEMANTIC_VALIDATION_FAILED: ErrorCategory.VALIDATION,
    ErrorCode.UNSUPPORTED_DIALECT: ErrorCategory.VALIDATION,

    ErrorCode.MULTIPLE_STATEMENTS: ErrorCategory.SECURITY,
    ErrorCode.NON_SELECT_STATEMENT: ErrorCategory.SECURITY,
    ErrorCode.UNSAFE_DANGEROUS_FUNCTION: ErrorCategory.SECURITY,
    ErrorCode.UNSAFE_DML_KEYWORD: ErrorCategory.SECURITY,
    ErrorCode.UNSAFE_SANDBOX_REJECTED: ErrorCategory.SECURITY,

    ErrorCode.QUERY_TIMEOUT: ErrorCategory.EXECUTION,
    ErrorCode.ROW_LIMIT_EXCEEDED: ErrorCategory.EXECUTION,
    ErrorCode.READ_ONLY_VIOLATION: ErrorCategory.EXECUTION,
    ErrorCode.PERMISSION_DENIED: ErrorCategory.EXECUTION,
    ErrorCode.DATABASE_NOT_FOUND: ErrorCategory.EXECUTION,
    ErrorCode.INVALID_RESULT_SHAPE: ErrorCategory.EXECUTION,
    ErrorCode.EXECUTION_FAILED: ErrorCategory.EXECUTION,
}

DESCRIPTORS: Mapping[ErrorCode, ErrorDescriptor] = MappingProxyType({
    code: ErrorDescriptor(code=code, category=category)
    for code, category in _CATEGORY_BY_CODE.items()
})


def describe(code) -> ErrorDescriptor:
    """Kodun descriptor'ını döner. Düz string de kabul eder."""
    try:
        return DESCRIPTORS[ErrorCode(code)]
    except (ValueError, KeyError) as e:
        raise UnknownErrorCodeError(f"Bilinmeyen error code: {code!r}") from e


def category_of(code) -> ErrorCategory:
    return describe(code).category


def codes_for_category(category: ErrorCategory) -> frozenset[ErrorCode]:
    return frozenset(
        code for code, desc in DESCRIPTORS.items() if desc.category is category
    )
