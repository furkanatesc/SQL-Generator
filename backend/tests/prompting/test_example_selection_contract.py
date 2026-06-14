import pytest
from dataclasses import FrozenInstanceError
from app.prompting.few_shot_contract import SQLFewShotExample
from app.prompting.example_selection_contract import (
    SQL_EXAMPLE_SELECTION_VERSION,
    SQLExampleSelectionConfig,
    SQLExampleSelectionCandidate,
    SQLExampleSelectionReason,
    SQLExampleSelectionResult,
    SQLExampleSelectionContractError
)


def test_sql_example_selection_version_is_v1():
    assert SQL_EXAMPLE_SELECTION_VERSION == "sql_example_selection_v1"


def test_selection_config_is_frozen():
    config = SQLExampleSelectionConfig(target_dialect="sqlite")
    assert config.target_dialect == "sqlite"
    
    with pytest.raises(FrozenInstanceError):
        config.target_dialect = "postgresql"  # type: ignore


def test_selection_result_is_frozen():
    ex = SQLFewShotExample(
        id="ex1",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=(),
        sql="SELECT 1",
        notes=(),
        tags=()
    )
    reason = SQLExampleSelectionReason(
        example_id="ex1",
        score=100,
        matched_signals=("intent_type_match",)
    )
    
    result = SQLExampleSelectionResult(
        target_dialect="sqlite",
        intent_type="selection",
        selected_examples=(ex,),
        selected_example_ids=("ex1",),
        rejected_example_ids=(),
        selection_reasons=(reason,),
        max_examples=3,
        selection_fingerprint="a" * 64,  # valid 64-character SHA256 hex string
        version=SQL_EXAMPLE_SELECTION_VERSION
    )
    
    assert result.target_dialect == "sqlite"
    with pytest.raises(FrozenInstanceError):
        result.target_dialect = "postgresql"  # type: ignore


def test_selection_result_rejects_invalid_fingerprint_length():
    ex = SQLFewShotExample(
        id="ex1",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=(),
        sql="SELECT 1",
        notes=(),
        tags=()
    )
    reason = SQLExampleSelectionReason(
        example_id="ex1",
        score=100,
        matched_signals=("intent_type_match",)
    )
    
    with pytest.raises(SQLExampleSelectionContractError) as exc_info:
        SQLExampleSelectionResult(
            target_dialect="sqlite",
            intent_type="selection",
            selected_examples=(ex,),
            selected_example_ids=("ex1",),
            rejected_example_ids=(),
            selection_reasons=(reason,),
            max_examples=3,
            selection_fingerprint="short_hash",  # invalid length
            version=SQL_EXAMPLE_SELECTION_VERSION
        )
    assert "selection_fingerprint must be a valid 64-character SHA256 hex string" in str(exc_info.value)


def test_selection_result_rejects_selected_example_dialect_mismatch():
    # ex dialect is postgresql, target_dialect is sqlite
    ex = SQLFewShotExample(
        id="ex1",
        dialect="postgresql",
        intent_type="selection",
        question="Select all?",
        schema_context=(),
        sql="SELECT 1",
        notes=(),
        tags=()
    )
    reason = SQLExampleSelectionReason(
        example_id="ex1",
        score=100,
        matched_signals=("intent_type_match",)
    )
    
    with pytest.raises(SQLExampleSelectionContractError) as exc_info:
        SQLExampleSelectionResult(
            target_dialect="sqlite",
            intent_type="selection",
            selected_examples=(ex,),
            selected_example_ids=("ex1",),
            rejected_example_ids=(),
            selection_reasons=(reason,),
            max_examples=3,
            selection_fingerprint="a" * 64,
            version=SQL_EXAMPLE_SELECTION_VERSION
        )
    assert "does not match target_dialect" in str(exc_info.value)
