import pytest
from app.database import init_db, get_db_connection
from app import workspace_repository as repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.commit()


def test_slugify_basic():
    assert repo.slugify("My Workspace") == "my-workspace"
    assert repo.slugify("  Trailing / punctuation!!  ") == "trailing-punctuation"
    assert repo.slugify("A___B  C") == "a-b-c"


def test_slugify_empty_falls_back_nonempty():
    s = repo.slugify("!!!")
    assert s and s.strip("-")  # non-empty, not just dashes


def test_create_and_get():
    ws = repo.create_workspace("Alpha", "alpha", "first")
    assert ws["id"] and ws["name"] == "Alpha" and ws["slug"] == "alpha"
    assert ws["description"] == "first"
    assert ws["created_at"] and ws["updated_at"]
    got = repo.get_workspace(ws["id"])
    assert got == ws


def test_get_missing_returns_none():
    assert repo.get_workspace("nope") is None


def test_duplicate_slug_raises():
    repo.create_workspace("Alpha", "alpha", None)
    with pytest.raises(repo.WorkspaceSlugConflict):
        repo.create_workspace("Alpha2", "alpha", None)


def test_get_by_slug():
    repo.create_workspace("Alpha", "alpha", None)
    assert repo.get_workspace_by_slug("alpha")["name"] == "Alpha"
    assert repo.get_workspace_by_slug("missing") is None


def test_list_and_count_pagination():
    for i in range(5):
        repo.create_workspace(f"W{i}", f"w{i}", None)
    assert repo.count_workspaces() == 5
    page = repo.list_workspaces(limit=2, offset=0)
    assert len(page) == 2
    page2 = repo.list_workspaces(limit=2, offset=2)
    assert len(page2) == 2
    # disjoint pages
    assert {w["id"] for w in page}.isdisjoint({w["id"] for w in page2})


def test_update_whitelist_and_timestamp():
    ws = repo.create_workspace("Alpha", "alpha", "d1")
    updated = repo.update_workspace(ws["id"], name="Alpha X", description="d2")
    assert updated["name"] == "Alpha X" and updated["description"] == "d2"
    assert updated["slug"] == "alpha"  # slug immutable in 30.1
    assert updated["updated_at"] >= ws["updated_at"]


def test_update_missing_returns_none():
    assert repo.update_workspace("nope", name="x") is None


def test_delete():
    ws = repo.create_workspace("Alpha", "alpha", None)
    assert repo.delete_workspace(ws["id"]) is True
    assert repo.get_workspace(ws["id"]) is None
    assert repo.delete_workspace(ws["id"]) is False
