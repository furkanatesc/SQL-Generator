import pytest
import hashlib
import socket
from app.prompting.structured_output_contract import SQLStructuredOutputResult
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.prompting.self_check_contract import (
    SQLSelfCheckConfig,
    SQLSelfCheckResult,
    SQLSelfCheckContractError,
    SQL_SELF_CHECK_VERSION,
)
from app.prompting.self_check_generator import SQLSelfCheckGenerator


def make_mock_structured_output(sql: str) -> SQLStructuredOutputResult:
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    return SQLStructuredOutputResult(
        sql_text=sql,
        sql_sha256=sql_sha,
        sql_char_count=len(sql),
        provider_name="openai",
        provider_model="gpt-4",
        finish_reason="stop",
        prompt_sha256=None,
        raw_text_sha256=raw_sha,
        warnings=(),
    )


def make_mock_generation_input(query: str, dialect: str = "sqlite") -> SQLGenerationInputResult:
    prompt = f"mock prompt for {query}"
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return SQLGenerationInputResult(
        raw_query=query,
        normalized_query=query.strip().lower(),
        intent_type="selection",
        target_dialect=dialect,  # type: ignore
        rendered_prompt=prompt,
        prompt_sha256=prompt_sha,
        prompt_char_count=len(prompt),
        constraints=(),
        source_section_types=(),
        source_item_ids=(),
    )


def test_generator_rejects_none_structured_output():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    gen_input = make_mock_generation_input("Select all users")
    
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        generator.generate(None, gen_input, config)  # type: ignore
    assert "structured_output cannot be None" in str(exc_info.value)


def test_generator_rejects_none_generation_input():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    
    with pytest.raises(SQLSelfCheckContractError) as exc_info:
        generator.generate(struct_output, None, config)  # type: ignore
    assert "generation_input cannot be None" in str(exc_info.value)


def test_generator_is_deterministic_for_same_input():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res1 = generator.generate(struct_output, gen_input, config)
    res2 = generator.generate(struct_output, gen_input, config)
    
    assert res1 == res2
    assert res1.self_check_prompt == res2.self_check_prompt


def test_generator_computes_self_check_prompt_sha256():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    expected_prompt_sha = hashlib.sha256(res.self_check_prompt.encode("utf-8")).hexdigest()
    
    assert res.self_check_prompt_sha256 == expected_prompt_sha


def test_generator_computes_self_check_prompt_char_count():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    assert res.self_check_prompt_char_count == len(res.self_check_prompt)


def test_generator_includes_intent_alignment_check():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    intent_items = [x for x in res.check_items if x.category == "intent_alignment"]
    assert len(intent_items) == 1
    assert intent_items[0].instruction == "Does the SQL answer the user intent?"
    assert "Does the SQL answer the user intent?" in res.self_check_prompt


def test_generator_includes_schema_alignment_check():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    schema_items = [x for x in res.check_items if x.category == "schema_alignment"]
    assert len(schema_items) == 2
    assert any("selected / allowed tables" in x.instruction for x in schema_items)
    assert any("avoid hallucinated columns" in x.instruction for x in schema_items)
    assert "Does the SQL only use selected / allowed tables?" in res.self_check_prompt
    assert "Does the SQL avoid hallucinated columns?" in res.self_check_prompt


def test_generator_includes_relationship_alignment_check():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    rel_items = [x for x in res.check_items if x.category == "relationship_alignment"]
    assert len(rel_items) == 1
    assert "joins consistent with selected relationships" in rel_items[0].instruction
    assert "Are joins consistent with selected relationships / join paths?" in res.self_check_prompt


def test_generator_includes_dialect_safety_check():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users", dialect="postgresql")
    
    res = generator.generate(struct_output, gen_input, config)
    
    dialect_items = [x for x in res.check_items if x.category == "dialect_safety"]
    assert len(dialect_items) == 1
    assert dialect_items[0].instruction == "Is the SQL compatible with the target dialect?"
    assert "Is the SQL compatible with the target dialect?" in res.self_check_prompt
    assert res.target_dialect == "postgresql"


def test_generator_includes_safety_guardrail_check():
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    safety_items = [x for x in res.check_items if x.category == "safety_guardrail"]
    assert len(safety_items) == 1
    assert "destructive or unsafe statements" in safety_items[0].instruction
    assert "Does the SQL avoid destructive or unsafe statements unless explicitly allowed?" in res.self_check_prompt


def test_generator_does_not_call_provider_or_network(monkeypatch):
    def block_socket(*args, **kwargs):
        raise RuntimeError("Network calls are blocked during tests.")
    monkeypatch.setattr(socket, "socket", block_socket)
    
    generator = SQLSelfCheckGenerator()
    config = SQLSelfCheckConfig()
    struct_output = make_mock_structured_output("SELECT id, name FROM users;")
    gen_input = make_mock_generation_input("Select all users")
    
    res = generator.generate(struct_output, gen_input, config)
    
    assert res.version == SQL_SELF_CHECK_VERSION
    assert res.sql_sha256 == struct_output.sql_sha256
    assert res.self_check_prompt_sha256 == hashlib.sha256(res.self_check_prompt.encode("utf-8")).hexdigest()
    assert res.self_check_prompt_char_count == len(res.self_check_prompt)
    
    assert tuple(item.category for item in res.check_items) == (
        "intent_alignment",
        "schema_alignment",
        "schema_alignment",
        "relationship_alignment",
        "dialect_safety",
        "safety_guardrail",
        "output_shape",
    )
