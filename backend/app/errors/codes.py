"""Hata kodları — taksonominin TEK doğruluk kaynağı (Sprint 27.2).

v1'de bu liste bir test dosyasında (test_error_type_taxonomy_contract.py)
yaşıyordu ve pipeline'ın gerçekte emit ettiği bir koddan habersizdi.
Artık production kodudur; testler buradan türetir.

StrEnum, (str, Enum) DEĞİL: (str, Enum) ile f"{code}" -> "ErrorCode.X" üretir
ve kod tabanı hata mesajlarını f-string ile kurar. StrEnum'da f"{code}" -> "x".

Kod değeri stage öneki İÇERMEZ (spec §2.3): stage ayrı bir eksendir.
"""
from enum import StrEnum


class ErrorCode(StrEnum):
    # --- INPUT ---
    INPUT_ERROR = "input_error"
    EXCEL_PARSE_ERROR = "excel_parse_error"

    # --- RETRIEVAL ---
    SCHEMA_PRUNING_FAILED = "schema_pruning_failed"
    SCHEMA_PRUNING_CRASHED = "schema_pruning_crashed"
    SCHEMA_CONTEXT_SELECTION_CRASHED = "schema_context_selection_crashed"

    # --- GENERATION ---
    LLM_API_ERROR = "llm_api_error"
    SQL_GENERATION_EXHAUSTED = "sql_generation_exhausted"

    # --- VALIDATION ---
    EMPTY_SQL = "empty_sql"
    SQL_PARSE_ERROR = "sql_parse_error"
    SYNTAX_ERROR = "syntax_error"
    MISSING_TABLE = "missing_table"
    MISSING_COLUMN = "missing_column"
    SEMANTIC_VALIDATION_FAILED = "semantic_validation_failed"
    UNSUPPORTED_DIALECT = "unsupported_dialect"

    # --- SECURITY ---
    MULTIPLE_STATEMENTS = "multiple_statements"
    NON_SELECT_STATEMENT = "non_select_statement"
    UNSAFE_DANGEROUS_FUNCTION = "unsafe_dangerous_function"
    UNSAFE_DML_KEYWORD = "unsafe_dml_keyword"
    UNSAFE_SANDBOX_REJECTED = "unsafe_sandbox_rejected"

    # --- EXECUTION ---
    QUERY_TIMEOUT = "query_timeout"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    READ_ONLY_VIOLATION = "read_only_violation"
    PERMISSION_DENIED = "permission_denied"
    DATABASE_NOT_FOUND = "database_not_found"
    INVALID_RESULT_SHAPE = "invalid_result_shape"
    EXECUTION_FAILED = "execution_failed"
