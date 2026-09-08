import pytest
from app.database import init_db, get_db_connection
from app import feedback_repository as repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_run_feedback")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_run_feedback")
        conn.commit()


def test_create_and_get():
    f = repo.create_feedback("run1", "incorrect", "wrong_join", "bad join", "SELECT 1")
    assert f["id"] and f["query_run_id"] == "run1" and f["verdict"] == "incorrect"
    assert f["category"] == "wrong_join"
    assert repo.get_feedback(f["id"])["id"] == f["id"]


def test_create_correct_minimal():
    f = repo.create_feedback("run1", "correct", None, None, None)
    assert f["verdict"] == "correct" and f["category"] is None
    resp = repo.row_to_response_dict(f)
    assert set(resp.keys()) == {"id", "query_run_id", "verdict", "category", "note",
                                "corrected_sql", "created_at"}


def test_list_filters_and_paginate():
    repo.create_feedback("run1", "correct", None, None, None)
    repo.create_feedback("run1", "incorrect", "other", "x", None)
    repo.create_feedback("run2", "correct", None, None, None)
    assert len(repo.list_feedback(50, 0)) == 3
    assert len(repo.list_feedback(50, 0, query_run_id="run1")) == 2
    assert len(repo.list_feedback(50, 0, verdict="correct")) == 2
    assert len(repo.list_feedback(1, 0, query_run_id="run1")) == 1


def test_delete():
    f = repo.create_feedback("run1", "correct", None, None, None)
    assert repo.delete_feedback(f["id"]) is True
    assert repo.get_feedback(f["id"]) is None
    assert repo.delete_feedback(f["id"]) is False
