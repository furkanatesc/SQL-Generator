import pytest
import hashlib
from dataclasses import FrozenInstanceError
from app.prompting.self_check_contract import (
    SQL_SELF_CHECK_VERSION,
    SQLSelfCheckConfig,
    SQLSelfCheckItem,
    SQLSelfCheckResult,
    SQLSelfCheckContractError,
)


def test_sql_self_check_version_is_v1():
    assert SQL_SELF_CHECK_VERSION == "sql_self_check_v1"


def test_self_check_config_is_frozen():
    config = SQLSelfCheckConfig(include_severity=True)
    assert config.include_severity is True
    with pytest.raises(FrozenInstanceError):
        config.include_severity = False  # type: ignore


def test_self_check_item_is_frozen():
    item = SQLSelfCheckItem(
        id="item-1",
        category="intent_alignment",
        severity="high",
        instruction="Does it match?"
    )
    assert item.id == "item-1"
    with pytest.raises(FrozenInstanceError):
        item.id = "item-2"  # type: ignore


def test_self_check_result_is_frozen():
    item = SQLSelfCheckItem(
        id="item-1",
        category="intent_alignment",
        severity="high",
        instruction="Does it match?"
    )
    prompt = "some self check prompt content"
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    sql_sha = "a" * 64
    
    result = SQLSelfCheckResult(
        target_dialect="sqlite",
        sql_sha256=sql_sha,
        input_version="input_v1",
        prompt_sha256=None,
        check_items=(item,),
        self_check_prompt=prompt,
        self_check_prompt_sha256=prompt_sha,
        self_check_prompt_char_count=len(prompt),
        warnings=(),
    )
    
    assert result.target_dialect == "sqlite"
    with pytest.raises(FrozenInstanceError):
        result.target_dialect = "postgresql"  # type: ignore


def test_self_check_item_rejects_empty_id():
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        SQLSelfCheckItem(
            id="",
            category="intent_alignment",
            severity="high",
            instruction="Does it match?"
        )
    assert "id' cannot be empty" in str(exc_info.value)


def test_self_check_item_rejects_empty_category():
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        SQLSelfCheckItem(
            id="item-1",
            category="",
            severity="high",
            instruction="Does it match?"
        )
    assert "category' cannot be empty" in str(exc_info.value)


def test_self_check_result_rejects_duplicate_check_item_ids():
    item1 = SQLSelfCheckItem(
        id="duplicate-id",
        category="intent_alignment",
        severity="high",
        instruction="Does it match?"
    )
    item2 = SQLSelfCheckItem(
        id="duplicate-id",
        category="schema_alignment",
        severity="high",
        instruction="Does it match columns?"
    )
    prompt = "some prompt content"
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    sql_sha = "a" * 64
    
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        SQLSelfCheckResult(
            target_dialect="sqlite",
            sql_sha256=sql_sha,
            input_version="input_v1",
            prompt_sha256=None,
            check_items=(item1, item2),
            self_check_prompt=prompt,
            self_check_prompt_sha256=prompt_sha,
            self_check_prompt_char_count=len(prompt),
            warnings=(),
        )
    assert "Duplicate check item ID" in str(exc_info.value)


def test_self_check_result_rejects_hash_mismatch():
    item = SQLSelfCheckItem(
        id="item-1",
        category="intent_alignment",
        severity="high",
        instruction="Does it match?"
    )
    prompt = "some prompt content"
    wrong_prompt_sha = "b" * 64
    sql_sha = "a" * 64
    
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        SQLSelfCheckResult(
            target_dialect="sqlite",
            sql_sha256=sql_sha,
            input_version="input_v1",
            prompt_sha256=None,
            check_items=(item,),
            self_check_prompt=prompt,
            self_check_prompt_sha256=wrong_prompt_sha,
            self_check_prompt_char_count=len(prompt),
            warnings=(),
        )
    assert "does not match the actual SHA256" in str(exc_info.value)


def test_self_check_result_rejects_char_count_mismatch():
    item = SQLSelfCheckItem(
        id="item-1",
        category="intent_alignment",
        severity="high",
        instruction="Does it match?"
    )
    prompt = "some prompt content"
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    sql_sha = "a" * 64
    
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        SQLSelfCheckResult(
            target_dialect="sqlite",
            sql_sha256=sql_sha,
            input_version="input_v1",
            prompt_sha256=None,
            check_items=(item,),
            self_check_prompt=prompt,
            self_check_prompt_sha256=prompt_sha,
            self_check_prompt_char_count=len(prompt) + 10,
            warnings=(),
        )
    assert "does not match the actual length" in str(exc_info.value)
