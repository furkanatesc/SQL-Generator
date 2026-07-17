"""Hata taksonomisi v2 (Sprint 27.2) — tek doğruluk kaynağı.

Yaprak katman: stdlib dışına import YOKTUR. app.trace bunu güvenle import eder.
"""
from app.errors.categories import ErrorCategory
from app.errors.codes import ErrorCode
from app.errors.registry import (
    DESCRIPTORS,
    ErrorDescriptor,
    UnknownErrorCodeError,
    category_of,
    codes_for_category,
    describe,
)

__all__ = [
    "DESCRIPTORS",
    "ErrorCategory",
    "ErrorCode",
    "ErrorDescriptor",
    "UnknownErrorCodeError",
    "category_of",
    "codes_for_category",
    "describe",
]
