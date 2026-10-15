"""Backup / restore of SQLGen's persistent state (Sprint 32.8).

Archive layout (`sqlgen-backup-<UTC timestamp>[-<label>].tar.gz`):

    manifest.json   format, created_at, app_version, per-DB schema_version, sha256+size per file
    app.db          app database snapshot (SQLite online backup API: consistent, WAL included)
    trace.db        trace database snapshot (if it exists)
    uploads/...     uploaded files
    qdrant/...      embedded Qdrant store — best effort (plain file copy; see docs)

Restore verifies checksums and SQLite integrity, refuses backups from a newer schema, takes a
safety backup of the current state, and writes databases through the SQLite backup API
(transactional, works while other connections exist). Only the fixed members above are ever
extracted; absolute paths, `..` and links are rejected.
"""
import datetime as dt
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from app.backup import paths
from app.migrations import APP_MIGRATIONS, TRACE_MIGRATIONS
from app.migrations.runner import inspect

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
PREFIX = "sqlgen-backup-"
SUFFIX = ".tar.gz"
DATABASES = {"app": ("app.db", APP_MIGRATIONS), "trace": ("trace.db", TRACE_MIGRATIONS)}
TREE_PREFIXES = ("uploads/", "qdrant/")
PRE_MIGRATION_KEEP = 3


class BackupError(Exception):
    pass


@dataclass
class VerifyResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    manifest: Optional[dict] = None


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sqlite_snapshot(src_path: str, dest_path: str) -> None:
    """Consistent copy of a live SQLite database (committed WAL content included)."""
    src = sqlite3.connect(f"file:{os.path.abspath(src_path)}?mode=ro", uri=True)
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _schema_version(db_path: str, migrations) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return inspect(conn, migrations).current
    finally:
        conn.close()


def _walk_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, root).replace(os.sep, "/")


def create_backup(dest_dir: Optional[str] = None, include_qdrant: bool = True, label: str = "") -> Path:
    dest = Path(dest_dir or paths.backup_dir())
    dest.mkdir(parents=True, exist_ok=True)
    from app.settings import get_settings

    manifest = {
        "format": FORMAT_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "app_version": get_settings().app_version,
        "databases": {},
        "files": {},
        "includes": {"uploads": 0, "qdrant": "excluded"},
    }
    name = f"{PREFIX}{_timestamp()}{'-' + label if label else ''}{SUFFIX}"
    archive = dest / name
    tmp_archive = dest / (name + ".partial")

    with tempfile.TemporaryDirectory() as tmp:
        members: List[tuple] = []  # (source path on disk, archive name)
        sources = {"app": paths.app_db_path(), "trace": paths.trace_db_path()}
        for key, (member, migrations) in DATABASES.items():
            if not os.path.isfile(sources[key]):
                continue
            snap = os.path.join(tmp, member)
            sqlite_snapshot(sources[key], snap)
            manifest["databases"][key] = {"file": member, "schema_version": _schema_version(snap, migrations)}
            members.append((snap, member))
        upload_root = paths.upload_dir()
        if os.path.isdir(upload_root):
            for full, rel in _walk_files(upload_root):
                if os.path.basename(rel).startswith(".ready_check_"):
                    continue
                members.append((full, f"uploads/{rel}"))
                manifest["includes"]["uploads"] += 1
        qdrant_root = paths.qdrant_dir()
        if include_qdrant and os.path.isdir(qdrant_root):
            for full, rel in _walk_files(qdrant_root):
                members.append((full, f"qdrant/{rel}"))
            manifest["includes"]["qdrant"] = "best_effort"

        for full, member in members:
            manifest["files"][member] = {"sha256": _sha256_file(full), "size": os.path.getsize(full)}

        with tarfile.open(tmp_archive, "w:gz") as tar:
            data = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo("manifest.json")
            info.size = len(data)
            info.mtime = int(dt.datetime.now().timestamp())
            tar.addfile(info, io.BytesIO(data))
            for full, member in members:
                tar.add(full, arcname=member, recursive=False)
    os.replace(tmp_archive, archive)
    logger.info("backup created: %s (%d files)", archive.name, len(manifest["files"]))
    return archive


def _is_safe_member(member: tarfile.TarInfo) -> bool:
    name = member.name
    if not member.isfile() or name.startswith("/") or "\\" in name:
        return False
    parts = PurePosixPath(name).parts
    if ".." in parts or not parts:
        return False
    return name in ("manifest.json", "app.db", "trace.db") or name.startswith(TREE_PREFIXES)


def read_manifest(archive) -> dict:
    with tarfile.open(archive) as tar:
        try:
            return json.loads(tar.extractfile("manifest.json").read())
        except KeyError as exc:
            raise BackupError("archive has no manifest.json") from exc


def verify_backup(archive) -> VerifyResult:
    errors: List[str] = []
    try:
        manifest = read_manifest(archive)
    except (BackupError, tarfile.TarError, OSError, json.JSONDecodeError) as exc:
        return VerifyResult(False, [f"unreadable archive: {type(exc).__name__}"])
    if manifest.get("format") != FORMAT_VERSION:
        errors.append(f"unsupported backup format {manifest.get('format')!r}")
    expected: Dict[str, dict] = manifest.get("files", {})
    seen = set()
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not _is_safe_member(member):
                errors.append(f"unsafe or unexpected archive member: {member.name}")
                continue
            if member.name == "manifest.json":
                continue
            seen.add(member.name)
            meta = expected.get(member.name)
            data = tar.extractfile(member).read()
            if meta is None:
                errors.append(f"{member.name}: not listed in manifest")
                continue
            if hashlib.sha256(data).hexdigest() != meta["sha256"] or len(data) != meta["size"]:
                errors.append(f"{member.name}: checksum mismatch")
                continue
            if member.name.endswith(".db") and "/" not in member.name:
                db_file = os.path.join(tmp, member.name)
                with open(db_file, "wb") as f:
                    f.write(data)
                try:
                    conn = sqlite3.connect(db_file)
                    try:
                        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                    finally:
                        conn.close()
                    if result != "ok":
                        errors.append(f"{member.name}: integrity check failed")
                except sqlite3.DatabaseError:
                    errors.append(f"{member.name}: not a valid SQLite database")
    for missing in sorted(set(expected) - seen):
        errors.append(f"{missing}: listed in manifest but missing from archive")
    return VerifyResult(not errors, errors, manifest)


def _restore_database(snapshot_path: str, target_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(target_path)) or ".", exist_ok=True)
    src = sqlite3.connect(snapshot_path)
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore_backup(archive, include_qdrant: bool = False, safety_backup: bool = True) -> dict:
    result = verify_backup(archive)
    if not result.ok:
        raise BackupError("backup verification failed: " + "; ".join(result.errors))
    manifest = result.manifest
    for key, info in manifest.get("databases", {}).items():
        latest = DATABASES[key][1][-1].version
        if info.get("schema_version", 0) > latest:
            raise BackupError(
                f"backup {key} database schema v{info['schema_version']} is newer than this release "
                f"supports (v{latest}); restore it with a newer release"
            )

    safety = None
    if safety_backup:
        safety = create_backup(dest_dir=str(Path(archive).parent), include_qdrant=include_qdrant, label="pre-restore")

    restored: List[str] = []
    targets = {"app.db": paths.app_db_path(), "trace.db": paths.trace_db_path()}
    upload_root = paths.upload_dir()
    qdrant_root = paths.qdrant_dir()
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.name != "manifest.json"]
        for member in members:
            if member.name in targets:
                snap = os.path.join(tmp, member.name)
                with open(snap, "wb") as f:
                    f.write(tar.extractfile(member).read())
                _restore_database(snap, targets[member.name])
                restored.append(member.name)
        uploads = [m for m in members if m.name.startswith("uploads/")]
        for member in uploads:
            dest = os.path.join(upload_root, *PurePosixPath(member.name).parts[1:])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(tar.extractfile(member).read())
        if uploads:
            restored.append(f"uploads ({len(uploads)} files)")
        qdrant = [m for m in members if m.name.startswith("qdrant/")]
        if include_qdrant and qdrant:
            if os.path.isdir(qdrant_root):
                shutil.rmtree(qdrant_root)
            for member in qdrant:
                dest = os.path.join(qdrant_root, *PurePosixPath(member.name).parts[1:])
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(tar.extractfile(member).read())
            restored.append(f"qdrant ({len(qdrant)} files)")
    logger.warning("restored backup %s: %s", Path(archive).name, ", ".join(restored))
    return {"restored": restored, "safety_backup": str(safety) if safety else None}


def list_backups(directory: Optional[str] = None) -> List[dict]:
    root = Path(directory or paths.backup_dir())
    if not root.is_dir():
        return []
    items = []
    for p in root.glob(f"{PREFIX}*{SUFFIX}"):
        items.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    # The UTC timestamp follows the prefix, so name order is chronological.
    return sorted(items, key=lambda i: i["name"], reverse=True)


def prune_backups(keep: int, directory: Optional[str] = None) -> List[str]:
    if keep < 0:
        raise ValueError("keep must be >= 0")
    removed = []
    for item in list_backups(directory)[keep:]:
        os.remove(item["path"])
        removed.append(item["name"])
    return removed


_PRE_MIGRATION = re.compile(r"\.pre-v(\d+)-(\d{8}T\d{6}\d*Z)\.bak$")


def backup_db_before_migration(db_path: str, target_version: int, keep: int = PRE_MIGRATION_KEEP) -> str:
    """`<db>.pre-v<target>-<ts>.bak` next to the database; only the newest `keep` are kept."""
    dest = f"{db_path}.pre-v{target_version}-{_timestamp()}.bak"
    sqlite_snapshot(db_path, dest)
    directory = os.path.dirname(os.path.abspath(db_path))
    base = os.path.basename(db_path)
    found = []
    for name in os.listdir(directory):
        if name.startswith(base + ".pre-v"):
            m = _PRE_MIGRATION.search(name)
            if m:
                found.append(((int(m.group(1)), m.group(2)), name))
    for _, name in sorted(found, reverse=True)[keep:]:
        os.remove(os.path.join(directory, name))
    logger.warning("backed up database before migrating to v%d: %s", target_version, os.path.basename(dest))
    return dest
