import pytest
import hashlib
from dataclasses import FrozenInstanceError
from app.prompting.few_shot_contract import (
    SQL_FEW_SHOT_VERSION,
    SQLFewShotExample,
    SQLFewShotExampleSet,
    SQLFewShotRenderConfig,
    SQLFewShotRenderResult,
    SQLFewShotContractError
)


def test_sql_few_shot_version_is_v1():
    assert SQL_FEW_SHOT_VERSION == "sql_few_shot_v1"


def test_few_shot_example_is_frozen():
    ex = SQLFewShotExample(
        id="ex_001",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=("tbl1",),
        sql="SELECT * FROM tbl1",
        notes=("note1",),
        tags=("tag1",)
    )
    assert ex.id == "ex_001"
    
    with pytest.raises(FrozenInstanceError):
        ex.id = "ex_002"  # type: ignore


def test_few_shot_example_set_is_frozen():
    ex = SQLFewShotExample(
        id="ex_001",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=("tbl1",),
        sql="SELECT * FROM tbl1",
        notes=("note1",),
        tags=("tag1",)
    )
    example_set = SQLFewShotExampleSet(examples=(ex,))
    assert example_set.examples == (ex,)
    
    with pytest.raises(FrozenInstanceError):
        example_set.examples = ()  # type: ignore


def test_few_shot_render_result_is_frozen():
    ex = SQLFewShotExample(
        id="ex_001",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=("tbl1",),
        sql="SELECT * FROM tbl1",
        notes=("note1",),
        tags=("tag1",)
    )
    text = "rendered prompt text"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    
    res = SQLFewShotRenderResult(
        dialect="sqlite",
        examples=(ex,),
        rendered_text=text,
        rendered_sha256=sha,
        rendered_char_count=len(text),
        example_ids=("ex_001",),
        tags=("tag1",),
        version=SQL_FEW_SHOT_VERSION
    )
    
    assert res.dialect == "sqlite"
    with pytest.raises(FrozenInstanceError):
        res.dialect = "postgresql"  # type: ignore


def test_few_shot_example_rejects_empty_id():
    with pytest.raises(SQLFewShotContractError) as exc_info:
        SQLFewShotExample(
            id="",
            dialect="sqlite",
            intent_type="selection",
            question="Select all?",
            schema_context=(),
            sql="SELECT 1",
            notes=(),
            tags=()
        )
    assert "Example 'id' cannot be empty" in str(exc_info.value)


def test_few_shot_example_rejects_empty_question():
    with pytest.raises(SQLFewShotContractError) as exc_info:
        SQLFewShotExample(
            id="ex_1",
            dialect="sqlite",
            intent_type="selection",
            question="   ",
            schema_context=(),
            sql="SELECT 1",
            notes=(),
            tags=()
        )
    assert "Example 'question' cannot be empty" in str(exc_info.value)


def test_few_shot_example_rejects_empty_sql():
    with pytest.raises(SQLFewShotContractError) as exc_info:
        SQLFewShotExample(
            id="ex_1",
            dialect="sqlite",
            intent_type="selection",
            question="Query?",
            schema_context=(),
            sql="",
            notes=(),
            tags=()
        )
    assert "Example 'sql' cannot be empty" in str(exc_info.value)


def test_few_shot_example_rejects_unsupported_dialect():
    with pytest.raises(SQLFewShotContractError) as exc_info:
        SQLFewShotExample(
            id="ex_1",
            dialect="mysql",
            intent_type="selection",
            question="Query?",
            schema_context=(),
            sql="SELECT 1",
            notes=(),
            tags=()
        )
    assert "Unsupported example dialect: 'mysql'" in str(exc_info.value)


def test_few_shot_example_set_rejects_duplicate_ids():
    ex1 = SQLFewShotExample(
        id="ex_001",
        dialect="sqlite",
        intent_type="selection",
        question="Select all?",
        schema_context=(),
        sql="SELECT 1",
        notes=(),
        tags=()
    )
    ex2 = SQLFewShotExample(
        id="ex_001",  # duplicate ID
        dialect="sqlite",
        intent_type="selection",
        question="Select another?",
        schema_context=(),
        sql="SELECT 2",
        notes=(),
        tags=()
    )
    
    with pytest.raises(SQLFewShotContractError) as exc_info:
        SQLFewShotExampleSet(examples=(ex1, ex2))
    assert "Duplicate example ID found in set: 'ex_001'" in str(exc_info.value)
