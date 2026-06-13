import hashlib
from app.prompting.prompt_render_contract import RenderedPromptResult, RenderedPromptSection, PROMPT_RENDER_VERSION
from app.sql_generation.sql_generation_input_contract import (
    SQLGenerationInputConfig,
    SQL_GENERATION_INPUT_VERSION,
)
from app.sql_generation.sql_generation_input_assembler import SQLGenerationInputAssembler
from app.sql_generation.sql_generation_provider_contract import (
    SQLGenerationProviderResult,
    SQL_GENERATION_PROVIDER_VERSION,
)
from app.sql_generation.sql_generation_provider import DeterministicFakeSQLGenerationProvider
from app.sql_generation.sql_generation_provider_runner import SQLGenerationProviderRunner


def test_sql_generation_input_to_provider_result_smoke():
    """
    E2E offline smoke test validating:
    RenderedPromptResult -> SQLGenerationInputResult -> SQLGenerationProviderResult
    """
    raw_query = "List customers with unpaid orders"
    normalized_query = "list customers with unpaid orders"
    intent_type = "list"

    sections = (
        RenderedPromptSection(
            section_type="system_instructions",
            title="System Instructions",
            rendered_text="## System Instructions\n- You are a precise and helpful Text-to-SQL assistant.",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="user_intent",
            title="User Intent",
            rendered_text="## User Intent\n- Intent Type: list",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="schema_context",
            title="Schema Context",
            rendered_text="## Schema Context\n- Table/Column: table:customers | Role: primary_table",
            source_item_ids=("table:customers", "column:customers.id"),
            required=True
        ),
        RenderedPromptSection(
            section_type="relationship_context",
            title="Relationship Context",
            rendered_text="## Relationship Context\n- Relationship: relationship:orders.customer_id->customers.id",
            source_item_ids=("relationship:orders.customer_id->customers.id",),
            required=True
        ),
        RenderedPromptSection(
            section_type="constraints",
            title="Constraints",
            rendered_text="## Constraints\n- Use only listed tables and columns.",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="output_contract",
            title="Output Contract",
            rendered_text="## Output Contract\n- Expected output: SQL string only.",
            source_item_ids=(),
            required=True
        ),
    )

    rendered_prompt = "\n\n".join(sec.rendered_text for sec in sections)

    rendered_result = RenderedPromptResult(
        raw_query=raw_query,
        normalized_query=normalized_query,
        intent_type=intent_type,
        rendered_prompt=rendered_prompt,
        rendered_sections=sections,
        prompt_render_version=PROMPT_RENDER_VERSION
    )

    input_config = SQLGenerationInputConfig(
        target_dialect="sqlite",
        max_prompt_chars=10000,
        require_sql_only_output=True,
        allow_dml=False,
        allow_ddl=False,
    )

    # 1. Assemble SQLGenerationInputResult
    assembler = SQLGenerationInputAssembler()
    input_result = assembler.assemble(rendered_result, input_config)

    # 2. Run through SQLGenerationProviderRunner with DeterministicFakeSQLGenerationProvider
    runner = SQLGenerationProviderRunner()
    fake_sql = "SELECT customers.id, customers.name FROM customers JOIN orders ON customers.id = orders.customer_id WHERE orders.status = 'unpaid';"
    provider = DeterministicFakeSQLGenerationProvider(fixed_sql=fake_sql)

    provider_id = "fake-sql-provider"
    model_id = "deterministic-fake-v1"

    provider_result = runner.run(
        input_result=input_result,
        provider=provider,
        provider_id=provider_id,
        model_id=model_id,
        temperature=0.0,
        max_output_tokens=150,
        metadata={"session_id": "test-session-99"},
        query_id="query-123",
    )

    # 3. Assertions
    assert provider_result.version == SQL_GENERATION_PROVIDER_VERSION
    assert provider_result.generated_sql_text == fake_sql

    # Hash propagation
    assert provider_result.prompt_sha256 == input_result.prompt_sha256
    assert provider_result.response.prompt_sha256 == input_result.prompt_sha256
    assert provider_result.request.prompt_sha256 == input_result.prompt_sha256

    expected_input_sha = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()
    assert provider_result.prompt_sha256 == expected_input_sha

    # Output hash check
    expected_output_sha = hashlib.sha256(fake_sql.encode("utf-8")).hexdigest()
    assert provider_result.output_sha256 == expected_output_sha
    assert provider_result.response.output_sha256 == expected_output_sha

    # Request assertions
    req = provider_result.request
    assert req.version == SQL_GENERATION_PROVIDER_VERSION
    assert req.input_version == SQL_GENERATION_INPUT_VERSION
    assert req.provider_id == provider_id
    assert req.model_id == model_id
    assert req.temperature == 0.0
    assert req.max_output_tokens == 150
    assert req.metadata == {"session_id": "test-session-99"}
    assert req.query_id == "query-123"

    # Response assertions
    resp = provider_result.response
    assert resp.version == SQL_GENERATION_PROVIDER_VERSION
    assert resp.provider_id == provider_id
    assert resp.model_id == model_id
    assert resp.finish_reason == "stop"
    assert resp.raw_text == fake_sql
    assert resp.latency_ms == 10
    assert resp.token_usage is not None
    assert resp.token_usage.prompt_tokens == 10
    assert resp.token_usage.completion_tokens == 5
    assert resp.token_usage.total_tokens == 15
