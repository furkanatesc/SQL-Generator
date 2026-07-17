"""run_pipeline sonucu error_code taşır (Sprint 27.2 T3)."""
from unittest.mock import MagicMock, patch

from app.errors import ErrorCode
from app.sql_pipeline import SQLGenerationPipeline


def test_input_error_sets_error_code_on_result():
    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(trace_store=trace_store)

    result = pipeline.run_pipeline(job_id="t", natural_query=None, excel_file_path=None)

    assert result["success"] is False
    assert result["error_code"] is ErrorCode.INPUT_ERROR
    assert result["error"]  # serbest metin mesaj korunuyor


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_generation_exhausted_sets_error_code(mock_prompt):
    llm = MagicMock()
    llm.generate_sql.side_effect = Exception("API Failed")
    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(trace_store=trace_store, llm_provider=llm)

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(job_id="t", natural_query="q", max_attempts=1)

    assert result["success"] is False
    assert result["error_code"] is ErrorCode.SQL_GENERATION_EXHAUSTED


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_leaves_error_code_none(mock_prompt):
    llm = MagicMock()
    response = MagicMock()
    response.sql = "SELECT id FROM users"
    llm.generate_sql.return_value = response
    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(trace_store=trace_store, llm_provider=llm)

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {
            "tables": {"users": {"columns": [{"name": "id", "type": "int",
                                              "primary_key": True}]}}}
        result = pipeline.run_pipeline(job_id="t", natural_query="q", max_attempts=1)

    assert result["success"] is True
    assert result["error_code"] is None


def test_schema_pruning_failure_sets_renamed_code():
    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(trace_store=trace_store)

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"error": "şema bulunamadı"}
        result = pipeline.run_pipeline(job_id="t", natural_query="q")

    assert result["success"] is False
    assert result["error_code"] is ErrorCode.SCHEMA_PRUNING_FAILED
    # v1 adı öldü:
    assert result["error_code"] != "schema_pruning_error"
    # 27.1w invariant'ı: pruning_error'da pruned_schema_tables BOŞ kalır.
    assert result["pruned_schema_tables"] == []


def test_redaction_preserves_the_error_code_type():
    """ErrorCode bir str alt sınıfıdır; redaksiyon onu düz string'e
    düşürmemelidir (Sprint 27.2 T3).

    Not: ErrorCode burada modül başındaki importtan (satır 4) kullanılır,
    yerelde YENİDEN import edilmez. tests/errors/test_errors_package_purity.py
    test session ortasında `app.errors` modüllerini sys.modules'dan silip
    yeniden import ediyor (kendi başına doğru bir davranış, ama global durumu
    değiştiriyor); fonksiyon içi bir `from app.errors import ErrorCode` o
    noktadan sonra farklı bir sınıf nesnesi (aynı değer, farklı identity)
    döndürüp `is` karşılaştırmasını sırayla-kırılgan hale getirir. Modül
    seviyesindeki referans collection zamanında (bu mutasyondan önce)
    bağlandığı için `app.trace.redaction` içindeki ErrorCode referansıyla
    tutarlı kalır."""
    from app.trace.redaction import redact_sensitive

    out = redact_sensitive({"error_code": ErrorCode.INPUT_ERROR}, {"gizli"})
    assert out["error_code"] is ErrorCode.INPUT_ERROR


def test_redaction_still_redacts_secrets_in_normal_strings():
    """Muafiyet YALNIZ ErrorCode'a; normal metinler redakte edilmeye devam eder."""
    from app.trace.redaction import redact_sensitive

    out = redact_sensitive({"error": "api_key=cok-gizli-deger"}, set())
    assert "cok-gizli-deger" not in out["error"]
    assert "[REDACTED]" in out["error"]
