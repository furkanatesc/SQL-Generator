import uuid

import pytest
from app.database import init_db, get_db_connection
from app import organization_repository as repo


def _clean():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
        conn.commit()


@pytest.fixture(autouse=True)
def _db():
    init_db()
    _clean()
    yield
    _clean()


def test_default_organization_exists():
    d = repo.get_default_organization()
    assert d["slug"] == repo.DEFAULT_ORGANIZATION_SLUG == "default"
    assert d["name"] == "Default"


def test_create_and_get():
    o = repo.create_organization("Acme", "acme", "first")
    assert o["id"] and o["name"] == "Acme" and o["slug"] == "acme"
    assert o["description"] == "first" and o["created_at"] and o["updated_at"]
    assert repo.get_organization(o["id"]) == o


def test_get_missing_returns_none():
    assert repo.get_organization("nope") is None


def test_slug_conflict():
    repo.create_organization("Acme", "acme", None)
    with pytest.raises(repo.OrganizationSlugConflict):
        repo.create_organization("Other", "acme", None)


def test_list_pagination():
    for i in range(3):
        repo.create_organization(f"O{i}", f"o{i}", None)
    assert len(repo.list_organizations(limit=2, offset=0)) == 2
    assert len(repo.list_organizations(limit=50, offset=0)) == 4  # + default


def test_update():
    o = repo.create_organization("Acme", "acme", None)
    u = repo.update_organization(o["id"], name="Acme2", description="d")
    assert u["name"] == "Acme2" and u["description"] == "d" and u["slug"] == "acme"
    assert repo.update_organization(o["id"])["name"] == "Acme2"
    assert repo.update_organization("nope", name="x") is None


def test_delete():
    o = repo.create_organization("Acme", "acme", None)
    assert repo.delete_organization(o["id"]) is True
    assert repo.get_organization(o["id"]) is None
    assert repo.delete_organization(o["id"]) is False


def test_default_protected():
    d = repo.get_default_organization()
    with pytest.raises(repo.DefaultOrganizationProtected):
        repo.delete_organization(d["id"])
    assert repo.get_organization(d["id"]) is not None


def test_in_use_blocks_delete():
    o = repo.create_organization("Acme", "acme", None)
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, organization_id, name, slug, description, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, o["id"], "W", "w", None, "t", "t"),
        )
        conn.commit()
    with pytest.raises(repo.OrganizationInUse):
        repo.delete_organization(o["id"])
    assert repo.get_organization(o["id"]) is not None
