"""Deterministic point ids + schema_ddl eviction/audit (Sprint 28.8, Task 3)."""
import pytest
import app.rag_manager as rm
from app.schema.reindex_planner import stable_point_id


class _FakePoint:
    def __init__(self, id, table_name):
        self.id = id
        self.payload = {"table_name": table_name}


class _FakeClient:
    def __init__(self):
        self.upserts = []          # list of (collection, [point_ids])
        self.deleted = []          # list of ids deleted
        self._scroll_points = []

    def get_collections(self):
        class _C:
            collections = []
        return _C()

    def create_collection(self, **k):
        pass

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, [p.id for p in points]))

    def delete(self, collection_name, points_selector):
        # points_selector is a PointIdsList; capture its ids
        self.deleted.extend(getattr(points_selector, "points", points_selector))

    def scroll(self, collection_name, limit=None, with_payload=True, offset=None):
        return (self._scroll_points, None)


@pytest.fixture
def rag(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(rm, "_global_qdrant_client", fake)
    # RAGManager.__init__ reuses the global client and calls _init_collections
    r = rm.RAGManager(embedding_client=object())
    return r, fake


def test_index_ddl_uses_stable_point_id(rag, monkeypatch):
    r, fake = rag
    # embedding_client is object(); give it a get_embedding
    r.embedding_client = type("E", (), {"get_embedding": lambda self, text, api_key=None: [0.0] * 2048})()
    r.index_ddl("users", "Table: users")
    assert fake.upserts[-1] == ("schema_ddl", [stable_point_id("users")])


def test_delete_schema_points_deletes_by_stable_id(rag):
    r, fake = rag
    r.delete_schema_points(["users", "orders"])
    assert set(fake.deleted) == {stable_point_id("users"), stable_point_id("orders")}


def test_audit_reports_orphaned_and_stale(rag):
    r, fake = rag
    fake._scroll_points = [
        _FakePoint(stable_point_id("users"), "users"),      # ok
        _FakePoint(999999, "orders"),                       # stale id
        _FakePoint(stable_point_id("gone"), "gone"),        # orphaned (not valid)
    ]
    audit = r.audit_schema_ddl_points({"users", "orders"})
    assert "gone" in audit["orphaned"]
    assert "orders" in audit["stale_id"]
    assert audit["total"] == 3


def test_prune_deletes_orphaned_and_stale(rag):
    r, fake = rag
    fake._scroll_points = [
        _FakePoint(stable_point_id("users"), "users"),      # keep
        _FakePoint(12345, "orders"),                        # stale id -> delete
        _FakePoint(stable_point_id("gone"), "gone"),        # orphan -> delete
    ]
    deleted = r.prune_schema_ddl_points({"users", "orders"})
    assert set(deleted) == {"orders", "gone"}
    assert set(fake.deleted) == {12345, stable_point_id("gone")}
