import hashlib
import pytest
from app.database import init_db, get_db_connection
from app import api_key_repository as repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM api_keys")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM api_keys")
        conn.commit()


def test_create_returns_raw_and_stores_only_hash():
    raw, row = repo.generate_and_create("ci")
    assert isinstance(raw, str) and len(raw) >= 16
    assert row["name"] == "ci" and row["key_prefix"] == raw[:8]
    assert row["key_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert "raw" not in row and row["key_hash"] != raw  # raw never stored


def test_verify_key_matches_active_and_not_after_revoke():
    raw, row = repo.generate_and_create("k")
    assert repo.verify_key(raw)["id"] == row["id"]
    assert repo.verify_key("wrong-key") is None
    repo.revoke_api_key(row["id"])
    assert repo.verify_key(raw) is None  # revoked no longer verifies


def test_revoke_idempotent_and_missing():
    raw, row = repo.generate_and_create("k")
    r1 = repo.revoke_api_key(row["id"])
    assert r1["revoked_at"] is not None
    r2 = repo.revoke_api_key(row["id"])  # idempotent
    assert r2["revoked_at"] == r1["revoked_at"]
    assert repo.revoke_api_key("nope") is None


def test_list_get_and_response_dict_never_expose_hash():
    raw, row = repo.generate_and_create("k")
    assert len(repo.list_api_keys(50, 0)) == 1
    assert repo.get_api_key(row["id"])["id"] == row["id"]
    resp = repo.row_to_response_dict(row)
    assert set(resp.keys()) == {"id", "name", "key_prefix", "created_at",
                                "revoked_at", "active"}
    assert resp["active"] is True and "key_hash" not in resp


def test_distinct_keys():
    raw1, r1 = repo.generate_and_create("a")
    raw2, r2 = repo.generate_and_create("b")
    assert raw1 != raw2 and r1["key_hash"] != r2["key_hash"]
