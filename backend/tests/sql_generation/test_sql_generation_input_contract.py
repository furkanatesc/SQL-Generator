import dataclasses
import pytest
from app.sql_generation.sql_generation_input_contract import (
    SQL_GENERATION_INPUT_VERSION,
    SQLGenerationInputConfig,
    SQLGenerationConstraint,
    SQLGenerationInputResult,
)


def test_sql_generation_input_version_is_v1():
    assert SQL_GENERATION_INPUT_VERSION == "sql_generation_input_v1"


def test_sql_generation_input_config_is_frozen():
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.target_dialect = "postgresql"  # type: ignore


def test_sql_generation_constraint_is_frozen():
    constraint = SQLGenerationConstraint(name="allow_dml", value="false")
    with pytest.raises(dataclasses.FrozenInstanceError):
        constraint.value = "true"  # type: ignore


def test_sql_generation_input_result_is_frozen():
    result = SQLGenerationInputResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt="prompt",
        prompt_sha256="sha",
        prompt_char_count=6,
        constraints=(),
        source_section_types=(),
        source_item_ids=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.intent_type = "ranking"  # type: ignore


def test_constraints_are_tuple_based():
    result = SQLGenerationInputResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt="prompt",
        prompt_sha256="sha",
        prompt_char_count=6,
        constraints=(),
        source_section_types=(),
        source_item_ids=(),
    )
    assert isinstance(result.constraints, tuple)


def test_source_section_types_are_tuple_based():
    result = SQLGenerationInputResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt="prompt",
        prompt_sha256="sha",
        prompt_char_count=6,
        constraints=(),
        source_section_types=(),
        source_item_ids=(),
    )
    assert isinstance(result.source_section_types, tuple)


def test_source_item_ids_are_tuple_based():
    result = SQLGenerationInputResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt="prompt",
        prompt_sha256="sha",
        prompt_char_count=6,
        constraints=(),
        source_section_types=(),
        source_item_ids=(),
    )
    assert isinstance(result.source_item_ids, tuple)
