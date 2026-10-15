"""Sprint 32.8 — Backup / Restore.

`python -m app.backup create|verify|list|restore|prune`: consistent SQLite snapshots via the
online backup API, uploads and (best-effort) the embedded Qdrant store in one `.tar.gz` with a
checksummed manifest; verified, version-checked, atomic restore with a safety backup; and an
automatic DB backup before pending migrations are applied.
"""
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from app.settings import get_settings


@pytest.fixture
def env(monkeypatch, tmp_path):
    from app.backup import paths
    from app.database import init_db

    dirs = {name: tmp_path / name for name in ("data", "uploads", "qdrant", "backups")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setenv("SQLGEN_DB_PATH", str(dirs["data"] / "sqlgen.db"))
    monkeypatch.setenv("NL2SQL_TRACE_DB_PATH", str(dirs["data"] / "traces.db"))
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", str(dirs["uploads"]))
    monkeypatch.setenv("NL2SQL_BACKUP_DIR", str(dirs["backups"]))
    monkeypatch.setattr(paths, "qdrant_dir", lambda: str(dirs["qdrant"]))
    get_settings.cache_clear()
    init_db()
    from app.trace.sqlite_store import SQLiteTraceStore

    SQLiteTraceStore(str(dirs["data"] / "traces.db")).close()
    (dirs["uploads"] / "q1.xlsx").write_bytes(b"excel-bytes")
    (dirs["qdrant"] / "collection").mkdir()
    (dirs["qdrant"] / "collection" / "points.bin").write_bytes(b"vectors")
    _sql(dirs["data"] / "sqlgen.db", "INSERT INTO configs (key, value) VALUES ('marker', 'before')")
    return dirs


def _sql(db, query, params=()):
    conn = sqlite3.connect(str(db))
    conn.execute(query, params)
    conn.commit()
    conn.close()


def _one(db, query):
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(query).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _members(archive):
    with tarfile.open(archive) as tar:
        return set(tar.getnames())


# --- create / manifest -------------------------------------------------------------------------

def test_create_contains_snapshots_files_and_manifest(env):
    from app.backup.core import create_backup, read_manifest
    from app.migrations import APP_MIGRATIONS, TRACE_MIGRATIONS

    archive = create_backup()
    assert archive.parent == env["backups"] and archive.name.startswith("sqlgen-backup-")
    names = _members(archive)
    assert {"manifest.json", "app.db", "trace.db", "uploads/q1.xlsx", "qdrant/collection/points.bin"} <= names
    m = read_manifest(archive)
    assert m["format"] == 1
    assert m["databases"]["app"]["schema_version"] == APP_MIGRATIONS[-1].version
    assert m["databases"]["trace"]["schema_version"] == TRACE_MIGRATIONS[-1].version
    assert m["includes"]["qdrant"] == "best_effort" and m["includes"]["uploads"] == 1
    assert set(m["files"]) == names - {"manifest.json"}
    assert all(len(f["sha256"]) == 64 for f in m["files"].values())


def test_snapshot_is_consistent_for_wal_database_with_open_writer(env):
    from app.backup.core import create_backup

    writer = sqlite3.connect(str(env["data"] / "sqlgen.db"))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("INSERT INTO configs (key, value) VALUES ('wal', 'committed')")
    writer.commit()  # committed but not checkpointed: lives only in the -wal file
    archive = create_backup()
    writer.close()
    out = env["backups"] / "x"
    with tarfile.open(archive) as tar:
        tar.extract("app.db", out)
    assert _one(out / "app.db", "SELECT value FROM configs WHERE key='wal'") == "committed"


def test_create_can_exclude_qdrant(env):
    from app.backup.core import create_backup, read_manifest

    archive = create_backup(include_qdrant=False)
    assert not any(n.startswith("qdrant/") for n in _members(archive))
    assert read_manifest(archive)["includes"]["qdrant"] == "excluded"


def test_missing_trace_db_is_skipped(env):
    from app.backup.core import create_backup, read_manifest

    (env["data"] / "traces.db").unlink()
    archive = create_backup()
    assert "trace.db" not in _members(archive)
    assert "trace" not in read_manifest(archive)["databases"]


# --- verify ------------------------------------------------------------------------------------

def test_verify_ok(env):
    from app.backup.core import create_backup, verify_backup

    result = verify_backup(create_backup())
    assert result.ok and result.errors == []


def _rewrite(archive, mutate):
    """Rebuild the archive applying mutate(name, bytes) -> bytes."""
    with tarfile.open(archive) as tar:
        items = [(m.name, tar.extractfile(m).read()) for m in tar.getmembers() if m.isfile()]
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in items:
            data = mutate(name, data)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_verify_detects_checksum_mismatch(env):
    from app.backup.core import create_backup, verify_backup

    archive = create_backup()
    _rewrite(archive, lambda n, d: b"tampered" if n == "uploads/q1.xlsx" else d)
    result = verify_backup(archive)
    assert not result.ok and any("uploads/q1.xlsx" in e for e in result.errors)


def test_verify_detects_corrupt_database(env):
    from app.backup.core import create_backup, verify_backup
    import hashlib

    archive = create_backup()

    def corrupt(name, data):
        return b"not a sqlite database" * 10 if name == "app.db" else data

    _rewrite(archive, corrupt)
    # fix the checksum so only the integrity check can catch it
    def fix_manifest(name, data):
        if name != "manifest.json":
            return data
        m = json.loads(data)
        bad = b"not a sqlite database" * 10
        m["files"]["app.db"] = {"sha256": hashlib.sha256(bad).hexdigest(), "size": len(bad)}
        return json.dumps(m).encode()

    _rewrite(archive, fix_manifest)
    result = verify_backup(archive)
    assert not result.ok and any("app.db" in e for e in result.errors)


# --- restore -----------------------------------------------------------------------------------

def test_restore_brings_data_back_with_safety_backup(env):
    from app.backup.core import create_backup, list_backups, restore_backup

    archive = create_backup()
    _sql(env["data"] / "sqlgen.db", "UPDATE configs SET value='after' WHERE key='marker'")
    (env["uploads"] / "q1.xlsx").write_bytes(b"changed")
    (env["uploads"] / "extra.xlsx").write_bytes(b"new file")

    result = restore_backup(archive)

    assert _one(env["data"] / "sqlgen.db", "SELECT value FROM configs WHERE key='marker'") == "before"
    assert (env["uploads"] / "q1.xlsx").read_bytes() == b"excel-bytes"
    assert (env["uploads"] / "extra.xlsx").exists()  # restore does not delete extra uploads
    assert result["safety_backup"] and Path(result["safety_backup"]).exists()
    assert "pre-restore" in Path(result["safety_backup"]).name
    assert len(list_backups()) == 2


def test_restore_skips_qdrant_unless_requested(env):
    from app.backup.core import create_backup, restore_backup

    archive = create_backup()
    points = env["qdrant"] / "collection" / "points.bin"
    points.write_bytes(b"newer vectors")
    restore_backup(archive, safety_backup=False)
    assert points.read_bytes() == b"newer vectors"
    restore_backup(archive, include_qdrant=True, safety_backup=False)
    assert points.read_bytes() == b"vectors"


def test_restore_refuses_backup_from_newer_schema(env):
    from app.backup.core import BackupError, create_backup, restore_backup

    archive = create_backup()

    def bump(name, data):
        if name != "manifest.json":
            return data
        m = json.loads(data)
        m["databases"]["app"]["schema_version"] = 999
        return json.dumps(m).encode()

    _rewrite(archive, bump)
    with pytest.raises(BackupError, match="newer"):
        restore_backup(archive, safety_backup=False)


def test_restore_refuses_unverifiable_backup(env):
    from app.backup.core import BackupError, create_backup, restore_backup

    archive = create_backup()
    _rewrite(archive, lambda n, d: b"x" if n == "app.db" else d)
    with pytest.raises(BackupError, match="verification"):
        restore_backup(archive, safety_backup=False)
    assert _one(env["data"] / "sqlgen.db", "SELECT value FROM configs WHERE key='marker'") == "before"


def test_restore_rejects_path_traversal(env):
    from app.backup.core import BackupError, create_backup, restore_backup

    archive = create_backup()
    with tarfile.open(archive) as tar:
        items = [(m.name, tar.extractfile(m).read()) for m in tar.getmembers() if m.isfile()]
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in items + [("uploads/../../evil.txt", b"x")]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(BackupError):
        restore_backup(archive, safety_backup=False)
    assert not (env["uploads"].parent.parent / "evil.txt").exists()


# --- list / prune ------------------------------------------------------------------------------

def test_list_and_prune(env):
    from app.backup.core import create_backup, list_backups, prune_backups

    created = [create_backup(include_qdrant=False) for _ in range(4)]
    listed = list_backups()
    assert [b["name"] for b in listed] == [p.name for p in reversed(created)]
    removed = prune_backups(keep=2)
    assert sorted(removed) == sorted(p.name for p in created[:2])
    assert [b["name"] for b in list_backups()] == [p.name for p in reversed(created[2:])]


# --- pre-migration backup ------------------------------------------------------------------------

def test_pending_migration_on_existing_db_is_backed_up_first(env, monkeypatch):
    from app.database import init_db
    from app.migrations import app_db
    from app.migrations.runner import Migration

    extra = Migration(len(app_db.APP_MIGRATIONS) + 1, "test_extra",
                      lambda c: c.execute("CREATE TABLE extra_t (id INTEGER)"))
    monkeypatch.setattr("app.database.APP_MIGRATIONS", app_db.APP_MIGRATIONS + (extra,))
    init_db()
    backups = sorted(env["data"].glob("sqlgen.db.pre-v*.bak"))
    assert len(backups) == 1 and f"pre-v{extra.version}-" in backups[0].name
    assert _one(backups[0], "SELECT value FROM configs WHERE key='marker'") == "before"
    assert _one(backups[0], "SELECT COUNT(*) FROM sqlite_master WHERE name='extra_t'") == 0


def test_no_pre_migration_backup_for_new_db_or_when_disabled(env, monkeypatch, tmp_path):
    from app.database import init_db
    from app.migrations import app_db
    from app.migrations.runner import Migration

    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "fresh.db"))
    init_db()
    assert not list(tmp_path.glob("fresh.db.pre-v*.bak"))

    monkeypatch.setenv("SQLGEN_DB_PATH", str(env["data"] / "sqlgen.db"))
    monkeypatch.setenv("NL2SQL_BACKUP_BEFORE_MIGRATION", "false")
    get_settings.cache_clear()
    extra = Migration(len(app_db.APP_MIGRATIONS) + 1, "test_extra", lambda c: None)
    monkeypatch.setattr("app.database.APP_MIGRATIONS", app_db.APP_MIGRATIONS + (extra,))
    init_db()
    assert not list(env["data"].glob("sqlgen.db.pre-v*.bak"))


def test_pre_migration_backups_keep_last_three(env):
    from app.backup.core import backup_db_before_migration

    db = env["data"] / "sqlgen.db"
    for version in range(10, 15):
        backup_db_before_migration(str(db), version)
    kept = sorted(p.name for p in env["data"].glob("sqlgen.db.pre-v*.bak"))
    assert len(kept) == 3 and all(any(f"pre-v{v}-" in k for k in kept) for v in (12, 13, 14))


# --- CLI ---------------------------------------------------------------------------------------

def test_cli_create_verify_list_restore(env, capsys):
    from app.backup.__main__ import main

    assert main(["create"]) == 0
    archive = json.loads(capsys.readouterr().out)["archive"]
    assert main(["verify", archive]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert main(["list"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert main(["restore", archive]) == 1  # refuses without --yes
    assert "--yes" in capsys.readouterr().err
    assert main(["restore", archive, "--yes", "--no-safety-backup"]) == 0
    capsys.readouterr()
    assert main(["prune", "--keep", "0"]) == 0
    capsys.readouterr()


def test_cli_verify_fails_on_tampered_archive(env, capsys):
    from app.backup.__main__ import main
    from app.backup.core import create_backup

    archive = create_backup()
    _rewrite(archive, lambda n, d: b"tampered" if n == "uploads/q1.xlsx" else d)
    assert main(["verify", str(archive)]) == 1
    capsys.readouterr()


def test_backup_settings_in_contract():
    from app.config_contract import known_env_names

    assert {"NL2SQL_BACKUP_DIR", "NL2SQL_BACKUP_BEFORE_MIGRATION"} <= known_env_names()
