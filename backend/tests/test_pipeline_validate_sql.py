"""validate_sql seam testleri (Sprint 27.4 T4).

Her retry_disposition dalini ayri ayri kilitler. Bu seam replay'in uretimle
AYNI dogrulamayi kosmasini saglar; sapma sessiz olurdu.
"""
import pytest

from app.sql_pipeline import SQLGenerationPipeline, ValidationOutcome


class _FakeSchemaManager:
    def get_schema(self):
        return {"tables": {}}


@pytest.fixture
def pipeline():
    return SQLGenerationPipeline(schema_manager=_FakeSchemaManager())


PRUNED = {
    "tables": {
        "orders": {
            "columns": [
                {"name": "id", "type": "INTEGER"},
                {"name": "total", "type": "NUMERIC"},
            ]
        }
    }
}


def test_valid_sql_returns_ok_disposition_and_pretty_printed(pipeline):
    outcome = pipeline.validate_sql("SELECT id FROM orders", PRUNED, "postgres")
    assert isinstance(outcome, ValidationOutcome)
    assert outcome.valid is True
    assert outcome.retry_disposition == "ok"
    assert outcome.validation_errors == []
    assert outcome.error_message is None
    assert outcome.pretty_printed is True
    assert "SELECT" in outcome.sql


def test_parse_error_yields_retry_disposition(pipeline):
    outcome = pipeline.validate_sql("SELEKT FROM WHERE", PRUNED, "postgres")
    assert outcome.valid is False
    assert outcome.retry_disposition == "retry"
    assert outcome.validation_errors
    assert outcome.error_message


def test_write_statement_yields_abort_disposition(pipeline):
    outcome = pipeline.validate_sql("DELETE FROM orders", PRUNED, "postgres")
    assert outcome.valid is False
    # Yazma denemesi retry ile duzelmez — dongu kesilir.
    assert outcome.retry_disposition == "abort"
    stages = {e.get("stage") for e in outcome.validation_errors}
    assert stages & {"sql_guardrail", "sql_sandbox_safety"}


def test_semantic_error_yields_retry_disposition(pipeline):
    outcome = pipeline.validate_sql(
        "SELECT nonexistent_column FROM orders", PRUNED, "postgres")
    assert outcome.valid is False
    assert outcome.retry_disposition == "retry"


def test_timings_keys_present_and_non_negative(pipeline):
    outcome = pipeline.validate_sql("SELECT id FROM orders", PRUNED, "postgres")
    assert set(outcome.timings) == {"validation", "security"}
    assert outcome.timings["validation"] >= 0
    assert outcome.timings["security"] >= 0


def test_log_callback_receives_messages_when_provided(pipeline):
    messages = []
    pipeline.validate_sql("SELECT id FROM orders", PRUNED, "postgres",
                          log_callback=lambda m, s: messages.append(m))
    assert any("AST" in m for m in messages)


def test_no_log_callback_is_safe(pipeline):
    outcome = pipeline.validate_sql("SELECT id FROM orders", PRUNED, "postgres",
                                    log_callback=None)
    assert outcome.valid is True


def test_oracle_dialect_uppercases_identifiers(pipeline):
    outcome = pipeline.validate_sql("select id from orders", PRUNED, "oracle")
    assert "ORDERS" in outcome.sql.upper()
