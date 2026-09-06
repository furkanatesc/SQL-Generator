"""Workspace persistence (Sprint 30.1).

Single-responsibility data access for the `workspaces` table, mirroring the
database.py sqlite idiom (get_db_connection + dict rows + column-whitelist
dynamic UPDATE). The workspace is the top-level container later Phase 11
resources will belong to; 30.1 keeps it standalone (no retro-scoping).
"""
from __future__ import annotations

import datetime
import re
import sqlite3
import uuid
from typing import Any, Optional

from app.database import get_db_connection


class WorkspaceSlugConflict(Exception):
    """Raised when creating a workspace whose slug already exists."""


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """lowercase, non-alphanumeric runs -> single '-', trimmed. Never returns
    an empty string (falls back to a uuid so the slug stays unique)."""
    s = _SLUG_STRIP.sub("-", name.lower()).strip("-")
    return s or uuid.uuid4().hex


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_workspace(name: str, slug: str, description: Optional[str]) -> dict:
    ws_id = uuid.uuid4().hex
    now = _now()
    # The UNIQUE(slug) column + IntegrityError handler below is the sole,
    # race-free guard against duplicate slugs (no pre-check needed).
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO workspaces (id, name, slug, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ws_id, name, slug, description, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:  # UNIQUE(slug) backstop against races
        raise WorkspaceSlugConflict(slug) from exc
    return get_workspace(ws_id)


def get_workspace(workspace_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return dict(row) if row else None


def get_workspace_by_slug(slug: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE slug = ?", (slug,)
        ).fetchone()
        return dict(row) if row else None


def list_workspaces(limit: int, offset: int) -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM workspaces ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


# Columns update_workspace may write. SET is built from this whitelist so user
# input never becomes a column name (mirrors database.py::_UPDATABLE_JOB_COLUMNS).
_UPDATABLE_WORKSPACE_COLUMNS = ("name", "description")


def update_workspace(
    workspace_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[dict]:
    provided: dict[str, Any] = {"name": name, "description": description}
    fields: list[str] = []
    values: list[Any] = []
    for col in _UPDATABLE_WORKSPACE_COLUMNS:
        if provided[col] is not None:
            fields.append(f"{col} = ?")
            values.append(provided[col])
    if not fields:  # nothing to update
        return get_workspace(workspace_id)
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(workspace_id)
    with get_db_connection() as conn:
        cur = conn.execute(
            f"UPDATE workspaces SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    return get_workspace(workspace_id)


def delete_workspace(workspace_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        conn.commit()
        return cur.rowcount > 0
