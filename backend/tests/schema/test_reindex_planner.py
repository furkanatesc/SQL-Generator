from app.schema.reindex_planner import (
    REINDEX_FINGERPRINT_VERSION, build_table_embedding_text,
    compute_embedding_fingerprint, stable_point_id, plan_reindex, ReindexPlan,
)


def _meta(cols, fks=()):
    return {"columns": [{"name": n, "type": t} for (n, t) in cols],
            "foreign_keys": [{"referenced_table": r} for r in fks]}


def test_embedding_text_matches_expected_format():
    t = build_table_embedding_text("users", _meta([("id", "INTEGER"), ("email", "TEXT")]))
    assert t == "Table: users | Columns: id (INTEGER), email (TEXT)"


def test_embedding_text_includes_relations():
    t = build_table_embedding_text("orders", _meta([("id", "INTEGER")], fks=["users"]))
    assert t == "Table: orders | Columns: id (INTEGER) | Relations: references users"


def test_embedding_text_column_without_type():
    t = build_table_embedding_text("t", {"columns": [{"name": "x"}], "foreign_keys": []})
    assert t == "Table: t | Columns: x"


def test_fingerprint_deterministic_and_model_sensitive():
    text = "Table: users | Columns: id (INTEGER)"
    a = compute_embedding_fingerprint(text, "model-A")
    assert a == compute_embedding_fingerprint(text, "model-A")
    assert a != compute_embedding_fingerprint(text, "model-B")


def test_fingerprint_version_prefixed():
    assert compute_embedding_fingerprint("x", "m", version="v1") != \
           compute_embedding_fingerprint("x", "m", version="v2")


def test_stable_point_id_deterministic():
    assert stable_point_id("users") == stable_point_id("users")
    assert stable_point_id("users") != stable_point_id("orders")
    assert isinstance(stable_point_id("users"), int)


def _schema(tables):
    return {"tables": tables, "graph": {"nodes": [], "edges": []}}


def test_plan_new_table_is_to_embed():
    sch = _schema({"users": _meta([("id", "INTEGER")])})
    plan = plan_reindex({}, sch, "m")
    assert plan.to_embed == ("users",)
    assert plan.to_keep == ()
    assert plan.to_delete == ()


def test_plan_unchanged_table_is_to_keep():
    sch = _schema({"users": _meta([("id", "INTEGER")])})
    text = build_table_embedding_text("users", sch["tables"]["users"])
    old = {"users": compute_embedding_fingerprint(text, "m")}
    plan = plan_reindex(old, sch, "m")
    assert plan.to_keep == ("users",)
    assert plan.to_embed == ()


def test_plan_changed_column_is_to_embed():
    old_sch = _schema({"users": _meta([("id", "INTEGER")])})
    old = {"users": compute_embedding_fingerprint(
        build_table_embedding_text("users", old_sch["tables"]["users"]), "m")}
    new_sch = _schema({"users": _meta([("id", "INTEGER"), ("email", "TEXT")])})
    plan = plan_reindex(old, new_sch, "m")
    assert plan.to_embed == ("users",)


def test_plan_removed_table_is_to_delete():
    old = {"users": "fp1", "orders": "fp2"}
    new_sch = _schema({"users": _meta([("id", "INTEGER")])})
    plan = plan_reindex(old, new_sch, "m")
    assert plan.to_delete == ("orders",)


def test_plan_model_change_re_embeds_all():
    sch = _schema({"users": _meta([("id", "INTEGER")])})
    old = {"users": compute_embedding_fingerprint(
        build_table_embedding_text("users", sch["tables"]["users"]), "old-model")}
    plan = plan_reindex(old, sch, "new-model")
    assert plan.to_embed == ("users",)
    assert plan.to_keep == ()


def test_plan_as_dict_shape():
    plan = ReindexPlan(to_embed=("a",), to_keep=("b",), to_delete=("c",))
    assert plan.as_dict() == {"to_embed": ["a"], "to_keep": ["b"], "to_delete": ["c"]}
