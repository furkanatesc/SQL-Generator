import pytest
from app.prompting.prompt_plan_contract import PromptPlanResult, PromptPlanSection
from app.prompting.prompt_renderer import PromptRenderer
from app.prompting.prompt_render_contract import PROMPT_RENDER_VERSION
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


def build_valid_sections():
    return (
        PromptPlanSection(
            section_type="system_instructions",
            title="System Instructions",
            content_items=("Instruction 1", "Instruction 2"),
            source_item_ids=(),
            required=True,
        ),
        PromptPlanSection(
            section_type="user_intent",
            title="User Intent",
            content_items=("Intent: list",),
            source_item_ids=(),
            required=True,
        ),
        PromptPlanSection(
            section_type="schema_context",
            title="Schema Context",
            content_items=("table: customers",),
            source_item_ids=("table:customers",),
            required=True,
        ),
        PromptPlanSection(
            section_type="relationship_context",
            title="Relationship Context",
            content_items=(),
            source_item_ids=(),
            required=True,
        ),
        PromptPlanSection(
            section_type="constraints",
            title="Constraints",
            content_items=("Constraint 1",),
            source_item_ids=(),
            required=True,
        ),
        PromptPlanSection(
            section_type="output_contract",
            title="Output Contract",
            content_items=("Output SQL",),
            source_item_ids=(),
            required=True,
        ),
    )


def test_renderer_success():
    renderer = PromptRenderer()
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=build_valid_sections(),
    )
    result = renderer.render(plan)

    assert result.prompt_render_version == PROMPT_RENDER_VERSION
    assert result.raw_query == "list customers"
    assert result.normalized_query == "list customers"
    assert result.intent_type == "list"

    # Check rendered text format
    expected_prompt = (
        "## System Instructions\n"
        "- Instruction 1\n"
        "- Instruction 2\n\n"
        "## User Intent\n"
        "- Intent: list\n\n"
        "## Schema Context\n"
        "- table: customers\n\n"
        "## Relationship Context\n\n"  # Renders header only because content_items is empty
        "## Constraints\n"
        "- Constraint 1\n\n"
        "## Output Contract\n"
        "- Output SQL"
    )
    assert result.rendered_prompt == expected_prompt
    assert len(result.rendered_sections) == 6
    assert result.rendered_sections[3].rendered_text == "## Relationship Context"


def test_renderer_empty_basic_fields():
    renderer = PromptRenderer()

    # Raw query empty
    plan = PromptPlanResult(
        raw_query="  ",
        normalized_query="list customers",
        intent_type="list",
        sections=build_valid_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Raw query cannot be empty."):
        renderer.render(plan)

    # Normalized query empty
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="",
        intent_type="list",
        sections=build_valid_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Normalized query cannot be empty."):
        renderer.render(plan)

    # Intent type empty
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type=" ",
        sections=build_valid_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Intent type cannot be empty."):
        renderer.render(plan)


def test_renderer_empty_sections():
    renderer = PromptRenderer()
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Prompt plan sections cannot be empty."):
        renderer.render(plan)


def test_renderer_invalid_section_order():
    renderer = PromptRenderer()
    sections = build_valid_sections()
    # Swap system_instructions and user_intent
    swapped_sections = (sections[1], sections[0]) + sections[2:]
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=swapped_sections,
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Invalid section order"):
        renderer.render(plan)


def test_renderer_missing_section():
    renderer = PromptRenderer()
    sections = build_valid_sections()
    # Exclude constraints section
    missing_sections = sections[:4] + (sections[5],)
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=missing_sections,
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Invalid section order"):
        renderer.render(plan)


def test_renderer_duplicate_section():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    # Replace last section with duplicate of first
    sections[5] = PromptPlanSection(
        section_type="system_instructions",
        title="Duplicate",
        content_items=("dup",),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Duplicate section type found"):
        renderer.render(plan)


def test_renderer_unknown_section():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    # Replace one section with an unknown type
    sections[3] = PromptPlanSection(
        section_type="unknown_type",  # type: ignore
        title="Unknown",
        content_items=("val",),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Unknown section type found"):
        renderer.render(plan)


def test_renderer_empty_section_type():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    sections[0] = PromptPlanSection(
        section_type="",  # type: ignore
        title="System Instructions",
        content_items=("Instruction 1",),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Section type cannot be empty."):
        renderer.render(plan)


def test_renderer_empty_section_title():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    sections[0] = PromptPlanSection(
        section_type="system_instructions",
        title="  ",
        content_items=("Instruction 1",),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="has empty title"):
        renderer.render(plan)


def test_renderer_invalid_source_item_ids_type():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    sections[0] = PromptPlanSection(
        section_type="system_instructions",
        title="System Instructions",
        content_items=("Instruction 1",),
        source_item_ids=["not-a-tuple"],  # type: ignore
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="source_item_ids must be a tuple"):
        renderer.render(plan)


def test_renderer_invalid_content_items_type():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    sections[0] = PromptPlanSection(
        section_type="system_instructions",
        title="System Instructions",
        content_items=["not-a-tuple"],  # type: ignore
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="content_items must be a tuple"):
        renderer.render(plan)


def test_renderer_required_section_empty_content():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    # Empty schema_context (which is required)
    sections[2] = PromptPlanSection(
        section_type="schema_context",
        title="Schema Context",
        content_items=(),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Required section 'schema_context' has no content items"):
        renderer.render(plan)


def test_renderer_relationship_context_empty_content_allowed():
    renderer = PromptRenderer()
    sections = list(build_valid_sections())
    # relationship_context is empty, which is allowed even if required=True
    sections[3] = PromptPlanSection(
        section_type="relationship_context",
        title="Relationship Context",
        content_items=(),
        source_item_ids=(),
        required=True,
    )
    plan = PromptPlanResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        sections=tuple(sections),
    )
    result = renderer.render(plan)
    assert result.rendered_sections[3].rendered_text == "## Relationship Context"
