"""Connection registry persistence (Sprint 30.2).

Persists SQLConnectionProfile-shaped records (secret-by-reference; never a raw
secret). Every write is validated by constructing the Phase 7 domain object
(app.evaluation.connection_abstraction.SQLConnectionProfile), so READ_ONLY
enforcement, endpoint/port checks, auth-mode/secret_ref rules and the raw-secret
scan all apply. Standalone: opens no live DB connection, resolves no secret.
"""
from __future__ import annotations

import datetime
import sqlite3
import uuid
from typing import Any, Optional

from app.database import get_db_connection
from app.evaluation.connection_abstraction import (
    SQLConnectionProfile,
    SQLConnectionEndpoint,
    SQLConnectionSecretRef,
    SQLConnectionAccessMode,
)


class ConnectionRefConflict(Exception):
    """Raised when creating a connection whose connection_ref already exists."""


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def build_profile(
    *, connection_ref, dialect, environment, host, port, database,
    auth_mode, secret_provider, secret_key, max_rows, timeout_seconds,
) -> SQLConnectionProfile:
    """Construct (and thereby validate) the domain profile. access_mode is always
    READ_ONLY. `dialect`/`environment`/`auth_mode` are passed as raw strings so
    SQLConnectionProfile.__post_init__ does the enum conversion AND wraps any bad
    value as SQLConnectionAbstractionContractError (not a bare ValueError)."""
    secret_ref = None
    if secret_provider is not None or secret_key is not None:
        secret_ref = SQLConnectionSecretRef(provider=secret_provider or "", key=secret_key or "")
    return SQLConnectionProfile(
        connection_ref=connection_ref,
        dialect=dialect,
        environment=environment,
        endpoint=SQLConnectionEndpoint(host=host, port=port, database=database),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=auth_mode,
        secret_ref=secret_ref,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
    )


def create_connection(
    *, connection_ref, workspace_id, name, dialect, environment, host, port,
    database, auth_mode, secret_provider, secret_key, max_rows, timeout_seconds,
) -> dict:
    # Validate via the domain model (raises on invalid input).
    build_profile(
        connection_ref=connection_ref, dialect=dialect, environment=environment,
        host=host, port=port, database=database, auth_mode=auth_mode,
        secret_provider=secret_provider, secret_key=secret_key,
        max_rows=max_rows, timeout_seconds=timeout_seconds,
    )
    cid = uuid.uuid4().hex
    now = _now()
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO connections (id, connection_ref, workspace_id, name,
                    dialect, environment, host, port, database, access_mode,
                    auth_mode, secret_provider, secret_key, max_rows,
                    timeout_seconds, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, connection_ref, workspace_id, name, dialect, environment,
                 host, port, database, "read_only", auth_mode, secret_provider,
                 secret_key, max_rows, timeout_seconds, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        # Only the UNIQUE(connection_ref) constraint maps to a 409 conflict; any
        # other integrity violation is a genuine error and must surface, not be
        # mislabeled as a duplicate.
        if "connection_ref" in str(exc):
            raise ConnectionRefConflict(connection_ref) from exc
        raise
    return get_connection(cid)


def get_connection(connection_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE id = ?", (connection_id,)
        ).fetchone()
        return dict(row) if row else None


def get_by_ref(connection_ref: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE connection_ref = ?", (connection_ref,)
        ).fetchone()
        return dict(row) if row else None


def list_connections(limit: int, offset: int, workspace_id: Optional[str] = None) -> list[dict]:
    with get_db_connection() as conn:
        if workspace_id is not None:
            rows = conn.execute(
                "SELECT * FROM connections WHERE workspace_id = ? "
                "ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                (workspace_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM connections ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]


_UPDATABLE_CONNECTION_COLUMNS = (
    "name", "host", "port", "database", "environment", "auth_mode",
    "secret_provider", "secret_key", "max_rows", "timeout_seconds",
)


def update_connection(connection_id: str, **fields: Any) -> Optional[dict]:
    row = get_connection(connection_id)
    if row is None:
        return None
    # Effective writes: provided non-None fields, restricted to the whitelist.
    writes = {
        k: v for k, v in fields.items()
        if k in _UPDATABLE_CONNECTION_COLUMNS and v is not None
    }
    # Transitioning auth_mode to NONE must clear the stored secret_ref, otherwise
    # the domain invariant (NONE => secret_ref is None) makes the state
    # unreachable by update. This is the one place a column is written to NULL.
    if writes.get("auth_mode") == "none":
        writes["secret_provider"] = None
        writes["secret_key"] = None
    if not writes:
        return row
    merged = {**row, **writes}
    # Re-validate the resulting profile (raises on invalid input).
    build_profile(
        connection_ref=merged["connection_ref"], dialect=merged["dialect"],
        environment=merged["environment"], host=merged["host"], port=merged["port"],
        database=merged["database"], auth_mode=merged["auth_mode"],
        secret_provider=merged["secret_provider"], secret_key=merged["secret_key"],
        max_rows=merged["max_rows"], timeout_seconds=merged["timeout_seconds"],
    )
    # `writes` keys are all from _UPDATABLE_CONNECTION_COLUMNS (whitelist) — safe.
    cols = list(writes.keys())
    sets = [f"{c} = ?" for c in cols] + ["updated_at = ?"]
    values = [writes[c] for c in cols] + [_now(), connection_id]
    with get_db_connection() as conn:
        conn.execute(f"UPDATE connections SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    return get_connection(connection_id)


def delete_connection(connection_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM connections WHERE id = ?", (connection_id,))
        conn.commit()
        return cur.rowcount > 0


def row_to_response_dict(row: dict) -> dict:
    """Shape a DB row into the API response dict: nested endpoint + secret_ref
    pointer, no flat secret columns. Never contains a raw secret."""
    secret_ref = None
    if row.get("secret_provider") is not None or row.get("secret_key") is not None:
        secret_ref = {"provider": row.get("secret_provider"), "key": row.get("secret_key")}
    return {
        "id": row["id"],
        "connection_ref": row["connection_ref"],
        "workspace_id": row["workspace_id"],
        "name": row["name"],
        "dialect": row["dialect"],
        "environment": row["environment"],
        "endpoint": {"host": row["host"], "port": row["port"], "database": row["database"]},
        "access_mode": row["access_mode"],
        "auth_mode": row["auth_mode"],
        "secret_ref": secret_ref,
        "max_rows": row["max_rows"],
        "timeout_seconds": row["timeout_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
