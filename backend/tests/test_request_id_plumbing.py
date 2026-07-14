from unittest.mock import MagicMock
from app.llm.fake_provider import DeterministicFakeLLMProvider
from app.sql_pipeline import SQLGenerationPipeline


def _pipeline_with_spy():
    pipeline = SQLGenerationPipeline(
        schema_manager=MagicMock(),
        llm_provider=DeterministicFakeLLMProvider(sql="SELECT 1"),
        trace_store=MagicMock(spec=["save"]))
    pipeline.schema_pruner = MagicMock()
    pipeline.schema_pruner.prune_schema.return_value = {
        "tables": {"users": {"columns": [{"name": "id", "type": "int"}]}},
        "estimated_tokens": 10}
    captured = {}
    original = pipeline._capture_trace_on_exit

    def spy(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    pipeline._capture_trace_on_exit = spy
    return pipeline, captured


def test_given_request_id_reaches_trace_capture():
    pipeline, captured = _pipeline_with_spy()
    pipeline.run_pipeline(job_id="j1", natural_query="kaç kullanıcı",
                          dialect="postgres", request_id="req_verilen")
    assert captured["request_id"] == "req_verilen"


def test_missing_request_id_is_minted_with_prefix():
    pipeline, captured = _pipeline_with_spy()
    pipeline.run_pipeline(job_id="j1", natural_query="kaç kullanıcı",
                          dialect="postgres")
    assert captured["request_id"].startswith("req_")
    assert len(captured["request_id"]) > 8


def test_background_task_receives_request_id_from_http_state():
    import inspect
    from app import main as app_main
    sig = inspect.signature(app_main.process_job_pipeline)
    assert "request_id" in sig.parameters
