from unittest.mock import MagicMock
from app.llm.fake_provider import DeterministicFakeLLMProvider
from app.sql_pipeline import SQLGenerationPipeline


def _mocked_pipeline():
    pipeline = SQLGenerationPipeline(
        schema_manager=MagicMock(),
        llm_provider=DeterministicFakeLLMProvider(sql="SELECT 1"),
        trace_store=None)
    pipeline.schema_pruner = MagicMock()
    pipeline.schema_pruner.prune_schema.return_value = {
        "tables": {"users": {"columns": [{"name": "id", "type": "int"}]}},
        "estimated_tokens": 10}
    return pipeline


def test_writer_critic_returns_timings_and_prompt_hash():
    pipeline = _mocked_pipeline()
    result = {"success": False, "aqr": None, "pruned_schema_tables": [],
              "generated_sql": "", "attempts": [], "error": None}
    wc, timings = pipeline._stage_writer_critic(
        aqr={"natural_query": "kaç kullanıcı var"}, natural_query="kaç kullanıcı var",
        previous_sql=None, prompt_schema_context="TABLE users(id int)",
        pruned_schema={"tables": {"users": {"columns": [{"name": "id", "type": "int"}]}}},
        dialect="postgres", api_key=None, max_attempts=3,
        log_callback=None, result=result)
    assert result["success"] is True
    assert set(timings) == {"prompt", "generation", "validation", "security"}
    assert all(isinstance(v, int) and v >= 0 for v in timings.values())
    assert isinstance(wc["prompt_sha256"], str) and len(wc["prompt_sha256"]) == 64
    assert wc["prompt_char_count"] > 0
    assert wc["last_generated_sql"]
