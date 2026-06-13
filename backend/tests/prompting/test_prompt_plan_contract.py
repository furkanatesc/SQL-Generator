import dataclasses
import pytest
from app.prompting.prompt_plan_contract import (
    PROMPT_PLAN_VERSION,
    PromptPlanSection,
    PromptPlanResult
)


def test_prompt_plan_version_is_v1():
    assert PROMPT_PLAN_VERSION == "prompt_plan_v1"


def test_prompt_plan_section_is_frozen():
    section = PromptPlanSection(
        section_type="system_instructions",
        title="Title",
        content_items=("item",),
        source_item_ids=(),
        required=True
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        section.title = "New Title"  # type: ignore


def test_prompt_plan_result_is_frozen():
    result = PromptPlanResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        sections=()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.intent_type = "ranking"  # type: ignore


def test_prompt_plan_sections_are_tuple_based():
    result = PromptPlanResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        sections=()
    )
    assert isinstance(result.sections, tuple)


def test_prompt_section_source_item_ids_are_tuple_based():
    section = PromptPlanSection(
        section_type="system_instructions",
        title="Title",
        content_items=("item",),
        source_item_ids=(),
        required=True
    )
    assert isinstance(section.source_item_ids, tuple)
