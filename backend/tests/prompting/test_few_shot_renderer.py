import pytest
import hashlib
import socket
from app.prompting.few_shot_contract import (
    SQLFewShotExample,
    SQLFewShotExampleSet,
    SQLFewShotRenderConfig,
    SQLFewShotContractError,
    SQL_FEW_SHOT_VERSION
)
from app.prompting.few_shot_renderer import SQLFewShotRenderer


def build_dummy_example(
    id: str,
    dialect: str = "sqlite",
    question: str = "Dummy question?",
    sql: str = "SELECT 1;",
    schema_context: tuple = ("table:tbl1",),
    notes: tuple = ("note1",),
    tags: tuple = ("tag1",)
) -> SQLFewShotExample:
    return SQLFewShotExample(
        id=id,
        dialect=dialect,
        intent_type="selection",
        question=question,
        schema_context=schema_context,
        sql=sql,
        notes=notes,
        tags=tags
    )


def test_few_shot_renderer_is_deterministic():
    renderer = SQLFewShotRenderer()
    ex1 = build_dummy_example("ex1", tags=("common", "sqlite"))
    ex2 = build_dummy_example("ex2", tags=("common", "join"))
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res1 = renderer.render(ex_set, config)
    res2 = renderer.render(ex_set, config)

    assert res1.rendered_text == res2.rendered_text
    assert res1.rendered_sha256 == res2.rendered_sha256
    assert res1.rendered_char_count == res2.rendered_char_count
    assert res1.example_ids == res2.example_ids
    assert res1.tags == res2.tags
    assert res1.version == SQL_FEW_SHOT_VERSION


def test_few_shot_renderer_preserves_example_order():
    renderer = SQLFewShotRenderer()
    ex1 = build_dummy_example("ex_first")
    ex2 = build_dummy_example("ex_second")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res = renderer.render(ex_set, config)
    assert res.example_ids == ("ex_first", "ex_second")
    assert res.rendered_text.startswith("Example ID: ex_first")
    assert "Example ID: ex_second" in res.rendered_text


def test_few_shot_renderer_computes_rendered_sha256():
    renderer = SQLFewShotRenderer()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res = renderer.render(ex_set, config)
    expected_sha = hashlib.sha256(res.rendered_text.encode("utf-8")).hexdigest()
    assert res.rendered_sha256 == expected_sha


def test_few_shot_renderer_computes_rendered_char_count():
    renderer = SQLFewShotRenderer()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res = renderer.render(ex_set, config)
    assert res.rendered_char_count == len(res.rendered_text)


def test_few_shot_renderer_outputs_example_ids_in_order():
    renderer = SQLFewShotRenderer()
    ex1 = build_dummy_example("id_a")
    ex2 = build_dummy_example("id_b")
    ex3 = build_dummy_example("id_c")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2, ex3))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res = renderer.render(ex_set, config)
    assert res.example_ids == ("id_a", "id_b", "id_c")


def test_few_shot_renderer_rejects_empty_examples_when_required():
    renderer = SQLFewShotRenderer()
    ex_set = SQLFewShotExampleSet(examples=())
    config = SQLFewShotRenderConfig(target_dialect="sqlite", required=True)

    with pytest.raises(SQLFewShotContractError) as exc_info:
        renderer.render(ex_set, config)
    assert "examples are required but the provided set is empty" in str(exc_info.value)


def test_few_shot_renderer_allows_empty_examples_when_not_required():
    renderer = SQLFewShotRenderer()
    ex_set = SQLFewShotExampleSet(examples=())
    config = SQLFewShotRenderConfig(target_dialect="sqlite", required=False)

    res = renderer.render(ex_set, config)
    assert res.rendered_text == ""
    assert res.rendered_char_count == 0
    assert res.rendered_sha256 == hashlib.sha256(b"").hexdigest()
    assert res.example_ids == ()
    assert res.tags == ()


def test_few_shot_renderer_rejects_dialect_mismatch():
    renderer = SQLFewShotRenderer()
    # ex dialect is postgresql, config dialect is sqlite
    ex = build_dummy_example("ex1", dialect="postgresql")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    with pytest.raises(SQLFewShotContractError) as exc_info:
        renderer.render(ex_set, config)
    assert "does not match config.target_dialect" in str(exc_info.value)


def test_few_shot_renderer_slices_max_examples():
    renderer = SQLFewShotRenderer()
    ex1 = build_dummy_example("ex1")
    ex2 = build_dummy_example("ex2")
    ex3 = build_dummy_example("ex3")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2, ex3))
    config = SQLFewShotRenderConfig(target_dialect="sqlite", max_examples=2)

    res = renderer.render(ex_set, config)
    assert res.example_ids == ("ex1", "ex2")
    assert len(res.examples) == 2


def test_few_shot_renderer_does_not_call_provider(monkeypatch):
    # Enforce network connection block using monkeypatch on socket
    def block_socket_connect(*args, **kwargs):
        raise RuntimeError("Network/provider call attempted!")
    monkeypatch.setattr(socket.socket, "connect", block_socket_connect)

    renderer = SQLFewShotRenderer()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLFewShotRenderConfig(target_dialect="sqlite")

    res = renderer.render(ex_set, config)
    assert res is not None
