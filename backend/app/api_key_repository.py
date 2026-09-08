"""API key management persistence (Sprint 30.8).

Managed, hashed, multiple API keys. Stores only the sha256 hash + an 8-char
prefix; the raw key is returned once by generate_and_create and never persisted.
sha256 (no salt) is appropriate for high-entropy random tokens (not passwords).
Inert: verify_key is a verification contract NOT wired into app.auth.verify_api_key.
"""
from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid
from typing import Optional

from app.database import get_db_connection


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_and_create(name: str) -> tuple[str, dict]:
    """Generate a new API key. Returns (raw_key, stored_row). The raw key is
    returned ONCE and never persisted — only its sha256 hash + prefix are stored."""
    raw = secrets.token_urlsafe(32)
    kid = uuid.uuid4().hex
    now = _now()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO api_keys (id, name, key_prefix, key_hash, created_at, revoked_at) "
            "VALUES (?, ?, ?, ?, ?, NULL)",
            (kid, name, raw[:8], _hash(raw), now),
        )
        conn.commit()
    return raw, get_api_key(kid)


def get_api_key(key_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return dict(row) if row else None


def list_api_keys(limit: int, offset: int) -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM api_keys ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_api_key(key_id: str) -> Optional[dict]:
    if get_api_key(key_id) is None:
        return None
    # Atomic conditional update: sets revoked_at only when still active, so it is
    # idempotent AND race-safe (concurrent revokes cannot double-write the timestamp).
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_now(), key_id),
        )
        conn.commit()
    return get_api_key(key_id)


def verify_key(raw: str) -> Optional[dict]:
    """Inert verification contract: return the ACTIVE key row matching raw, else
    None. NOT wired into app.auth.verify_api_key (live enforcement deferred)."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
            (_hash(raw),),
        ).fetchone()
        return dict(row) if row else None


def row_to_response_dict(row: dict) -> dict:
    """Metadata only — NEVER the raw key or key_hash."""
    return {
        "id": row["id"],
        "name": row["name"],
        "key_prefix": row["key_prefix"],
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
        "active": row["revoked_at"] is None,
    }
