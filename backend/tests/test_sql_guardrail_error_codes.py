"""Guardrail v2 kod sözleşmesi (Sprint 27.2 T2)."""
from app.errors import ErrorCategory, ErrorCode, category_of
from app.sql_guardrail import SQLGuardrailValidator


def _first(sql):
    errors = SQLGuardrailValidator.validate(sql)
    assert errors, f"beklenen hata üretilmedi: {sql!r}"
    return errors[0]


# Guardrail dallarını tetikleyen GERÇEK SQL'ler (plan yazımında fiilen
# çalıştırılarak doğrulandı — tahmin değil):
#   "SELECT pg_sleep(10)"                                  -> dangerous_function
#   "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d" -> dml_keyword
#   "DELETE FROM users"                                    -> non_select_statement
#
# Dikkat: "DELETE FROM users" dml_keyword dalına DÜŞMEZ. exp.Select tip kontrolü
# (sql_guardrail.py:92) DML node taramasından ÖNCE gelir, o yüzden çıplak DML
# non_select_statement olur. dml_keyword dalı yalnız statement'ın kendisi SELECT
# iken İÇİNDE yasaklı node bulunduğunda tetiklenir — CTE içine gömülü DELETE
# tam olarak bu vakadır ve guardrail'in var oluş sebebidir.

DML_IN_CTE = "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d"


def test_dangerous_function_has_its_own_code():
    err = _first("SELECT pg_sleep(10)")
    assert err["type"] is ErrorCode.UNSAFE_DANGEROUS_FUNCTION
    assert err["stage"] == "sql_guardrail"
    assert err["details"]["reason"] == "dangerous_function_detected"
    assert err["details"]["function"] == "PG_SLEEP"


def test_dml_keyword_has_its_own_code():
    err = _first(DML_IN_CTE)
    assert err["type"] is ErrorCode.UNSAFE_DML_KEYWORD
    assert err["stage"] == "sql_guardrail"
    assert err["details"]["reason"] == "dml_keyword_detected"


def test_the_three_former_unsafe_sql_causes_are_now_distinct():
    # v1'de bu üçü de "unsafe_sql"di ve ayrım yalnız details.reason'daydı.
    # (Üçüncüsü, sandbox reddi, sql_pipeline.py:434'te — T3'te ayrılıyor.)
    danger = _first("SELECT pg_sleep(10)")["type"]
    dml = _first(DML_IN_CTE)["type"]
    assert danger is ErrorCode.UNSAFE_DANGEROUS_FUNCTION
    assert dml is ErrorCode.UNSAFE_DML_KEYWORD
    assert danger is not dml


def test_unsafe_sql_is_never_emitted_anymore():
    for sql in ("SELECT pg_sleep(10)", DML_IN_CTE, "DELETE FROM users",
                "DROP TABLE users"):
        for err in SQLGuardrailValidator.validate(sql):
            assert err["type"] != "unsafe_sql"


def test_bare_dml_is_still_non_select_not_dml_keyword():
    # Davranış DEĞİŞMEDİ, yalnız kod adları değişti. Bu testin amacı o
    # davranışı kilitlemek: DELETE FROM users tip kontrolüne takılır.
    err = _first("DELETE FROM users")
    assert err["type"] is ErrorCode.NON_SELECT_STATEMENT
    assert err["details"]["reason"] == "statement_type_mismatch"


def test_all_guardrail_codes_are_registry_known():
    samples = [
        "SELECT pg_sleep(10)", DML_IN_CTE, "DELETE FROM users",
        "DROP TABLE users", "SELECT 1; SELECT 2;", "", "SELECT * FROM",
    ]
    for sql in samples:
        for err in SQLGuardrailValidator.validate(sql):
            assert isinstance(err["type"], ErrorCode)
            category_of(err["type"])  # bilinmiyorsa UnknownErrorCodeError atar


def test_guardrail_codes_keep_working_as_plain_strings():
    # StrEnum garantisi: mevcut çağrı yerleri string gibi kullanmaya devam edebilir.
    err = _first("SELECT 1; SELECT 2;")
    assert err["type"] == "multiple_statements"
    assert f"{err['type']}" == "multiple_statements"


def test_dangerous_function_is_security_category():
    assert category_of(ErrorCode.UNSAFE_DANGEROUS_FUNCTION) is ErrorCategory.SECURITY
    assert category_of(ErrorCode.UNSAFE_DML_KEYWORD) is ErrorCategory.SECURITY
