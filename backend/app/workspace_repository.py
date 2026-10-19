"""Workspace persistence (Sprint 30.1).

Single-responsibility data access for the `workspaces` table, mirroring the
database.py sqlite idiom (get_db_connection + dict rows + column-whitelist
dynamic UPDATE). The workspace is the top-level container later Phase 11
resources belong to; since 33.0 each workspace belongs to an organization.
"""
from __future__ import annotations

import datetime
import re
import sqlite3
import uuid
from typing import Any, Optional

from app.database import get_db_connection
from app.organization_repository import DEFAULT_ORGANIZATION_SLUG


class WorkspaceSlugConflict(Exception):
    """Raised when the slug already exists within the organization."""


class UnknownOrganization(Exception):
    """Raised when creating a workspace in an organization that does not exist."""


class WorkspaceInUse(Exception):
    """Raised when deleting a workspace that still has connections."""


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """lowercase, non-alphanumeric runs -> single '-', trimmed. Never returns
    an empty string (falls back to a uuid so the slug stays unique)."""
    s = _SLUG_STRIP.sub("-", name.lower()).strip("-")
    return s or uuid.uuid4().hex


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_workspace(
    name: str,
    slug: str,
    description: Optional[str],
    organization_id: Optional[str] = None,
) -> dict:
    """Create a workspace inside an organization (None -> the default org).

    Raises UnknownOrganization if the organization does not exist. The org
    check and the insert share one write transaction (BEGIN IMMEDIATE).
    """
    ws_id = uuid.uuid4().hex
    now = _now()
    # UNIQUE(organization_id, slug) + the IntegrityError handler below is the
    # sole, race-free guard against duplicate slugs within an organization.
    try:
        with get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if organization_id is None:
                org_row = conn.execute(
                    "SELECT id FROM organizations WHERE slug = ?",
                    (DEFAULT_ORGANIZATION_SLUG,),
                ).fetchone()
            else:
                org_row = conn.execute(
                    "SELECT id FROM organizations WHERE id = ?", (organization_id,)
                ).fetchone()
            if org_row is None:
                conn.rollback()
                raise UnknownOrganization(organization_id)
            conn.execute(
                """
                INSERT INTO workspaces (id, organization_id, name, slug, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ws_id, org_row["id"], name, slug, description, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:  # UNIQUE(organization_id, slug) backstop
        raise WorkspaceSlugConflict(slug) from exc
    return get_workspace(ws_id)


def get_workspace(workspace_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return dict(row) if row else None


def get_workspace_by_slug(organization_id: str, slug: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE organization_id = ? AND slug = ?",
            (organization_id, slug),
        ).fetchone()
        return dict(row) if row else None


def list_workspaces(
    limit: int, offset: int, organization_id: Optional[str] = None
) -> list[dict]:
    where = "WHERE organization_id = ? " if organization_id is not None else ""
    params: tuple = (organization_id,) if organization_id is not None else ()
    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM workspaces {where}ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
            (*params, limit, offset),
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
    """Delete a workspace; False if absent, WorkspaceInUse if connections use it.

    The in-use check and the delete are one conditional statement, so a
    connection created concurrently cannot be orphaned.
    """
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM workspaces WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM connections WHERE workspace_id = ?)",
            (workspace_id, workspace_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            return True
        exists = conn.execute(
            "SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        if exists:
            raise WorkspaceInUse(workspace_id)
        return False
