"""Organization persistence (Sprint 33.0).

Data access for the `organizations` table (mirrors workspace_repository).
Organizations are the top-level tenant container; workspaces belong to one.
No SQL FOREIGN KEY: the in-use check on delete is enforced here.
"""
from __future__ import annotations

import datetime
import sqlite3
import uuid
from typing import Any, Optional

from app.database import get_db_connection

DEFAULT_ORGANIZATION_SLUG = "default"


class OrganizationSlugConflict(Exception):
    """Raised when creating an organization whose slug already exists."""


class OrganizationInUse(Exception):
    """Raised when deleting an organization that still owns workspaces."""


class DefaultOrganizationProtected(Exception):
    """Raised when attempting to delete the default organization."""


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_organization(name: str, slug: str, description: Optional[str]) -> dict:
    org_id = uuid.uuid4().hex
    now = _now()
    # UNIQUE(slug) + IntegrityError is the sole race-free duplicate guard.
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO organizations (id, name, slug, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (org_id, name, slug, description, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise OrganizationSlugConflict(slug) from exc
    return get_organization(org_id)


def get_organization(organization_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM organizations WHERE id = ?", (organization_id,)
        ).fetchone()
        return dict(row) if row else None


def get_default_organization() -> dict:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM organizations WHERE slug = ?", (DEFAULT_ORGANIZATION_SLUG,)
        ).fetchone()
        return dict(row)


def list_organizations(limit: int, offset: int) -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM organizations ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


_UPDATABLE_ORGANIZATION_COLUMNS = ("name", "description")


def update_organization(
    organization_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[dict]:
    provided: dict[str, Any] = {"name": name, "description": description}
    fields: list[str] = []
    values: list[Any] = []
    for col in _UPDATABLE_ORGANIZATION_COLUMNS:
        if provided[col] is not None:
            fields.append(f"{col} = ?")
            values.append(provided[col])
    if not fields:
        return get_organization(organization_id)
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(organization_id)
    with get_db_connection() as conn:
        cur = conn.execute(
            f"UPDATE organizations SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    return get_organization(organization_id)


def delete_organization(organization_id: str) -> bool:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT slug FROM organizations WHERE id = ?", (organization_id,)
        ).fetchone()
        if row is None:
            return False
        if row["slug"] == DEFAULT_ORGANIZATION_SLUG:
            raise DefaultOrganizationProtected(organization_id)
        used = conn.execute(
            "SELECT 1 FROM workspaces WHERE organization_id = ? LIMIT 1",
            (organization_id,),
        ).fetchone()
        if used:
            raise OrganizationInUse(organization_id)
        cur = conn.execute("DELETE FROM organizations WHERE id = ?", (organization_id,))
        conn.commit()
        return cur.rowcount > 0
