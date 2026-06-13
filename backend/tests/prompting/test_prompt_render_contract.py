import dataclasses
import pytest
from app.prompting.prompt_render_contract import (
    PROMPT_RENDER_VERSION,
    RenderedPromptSection,
    RenderedPromptResult
)


def test_prompt_render_version_is_v1():
    assert PROMPT_RENDER_VERSION == "prompt_render_v1"


def test_rendered_prompt_section_is_frozen():
    section = RenderedPromptSection(
        section_type="system_instructions",
        title="Title",
        rendered_text="rendered",
        source_item_ids=(),
        required=True
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        section.title = "New Title"  # type: ignore


def test_rendered_prompt_result_is_frozen():
    result = RenderedPromptResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        rendered_prompt="prompt",
        rendered_sections=()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.intent_type = "ranking"  # type: ignore


def test_rendered_sections_are_tuple_based():
    result = RenderedPromptResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        rendered_prompt="prompt",
        rendered_sections=()
    )
    assert isinstance(result.rendered_sections, tuple)


def test_source_item_ids_are_tuple_based():
    section = RenderedPromptSection(
        section_type="system_instructions",
        title="Title",
        rendered_text="rendered",
        source_item_ids=(),
        required=True
    )
    assert isinstance(section.source_item_ids, tuple)
