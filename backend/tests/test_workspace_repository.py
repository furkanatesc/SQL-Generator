import pytest
from app.database import init_db, get_db_connection
from app import workspace_repository as repo
from app import organization_repository as org_repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
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
    default = org_repo.get_default_organization()
    assert repo.get_workspace_by_slug(default["id"], "alpha")["name"] == "Alpha"
    assert repo.get_workspace_by_slug(default["id"], "missing") is None
    other = org_repo.create_organization("Other", "other", None)
    assert repo.get_workspace_by_slug(other["id"], "alpha") is None


def test_list_pagination():
    for i in range(5):
        repo.create_workspace(f"W{i}", f"w{i}", None)
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


def test_create_defaults_to_default_org():
    ws = repo.create_workspace("Alpha", "alpha", None)
    assert ws["organization_id"] == org_repo.get_default_organization()["id"]


def test_create_unknown_org_raises():
    with pytest.raises(repo.UnknownOrganization):
        repo.create_workspace("Alpha", "alpha", None, organization_id="nope")


def test_same_slug_in_two_orgs_ok_same_org_conflicts():
    other = org_repo.create_organization("Other", "other", None)
    a = repo.create_workspace("A", "same", None)
    b = repo.create_workspace("B", "same", None, organization_id=other["id"])
    assert a["organization_id"] != b["organization_id"]
    with pytest.raises(repo.WorkspaceSlugConflict):
        repo.create_workspace("C", "same", None, organization_id=other["id"])


def test_list_filters_by_organization():
    other = org_repo.create_organization("Other", "other", None)
    repo.create_workspace("A", "a", None)
    b = repo.create_workspace("B", "b", None, organization_id=other["id"])
    rows = repo.list_workspaces(limit=10, offset=0, organization_id=other["id"])
    assert [r["id"] for r in rows] == [b["id"]]
    assert len(repo.list_workspaces(limit=10, offset=0)) == 2


def _add_connection(workspace_id):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO connections (id, workspace_id, connection_ref, name, dialect, "
            "environment, host, port, database, access_mode, auth_mode, max_rows, "
            "timeout_seconds, created_at, updated_at) "
            "VALUES ('c1', ?, 'r', 'n', 'postgresql', 'local', 'h', 1, 'd', 'read_only', "
            "'secret_ref', 10, 1.0, 't', 't')",
            (workspace_id,),
        )
        conn.commit()


def test_delete_in_use_raises_and_keeps_workspace():
    ws = repo.create_workspace("Alpha", "alpha", None)
    _add_connection(ws["id"])
    with pytest.raises(repo.WorkspaceInUse):
        repo.delete_workspace(ws["id"])
    assert repo.get_workspace(ws["id"]) is not None
