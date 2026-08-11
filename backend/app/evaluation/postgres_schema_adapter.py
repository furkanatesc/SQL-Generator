"""Sprint 29.0 — Contract-first PostgreSQL schema introspection adapter.

The introspection twin of the Sprint 25.8 execution adapter
(``postgres_adapter.py``). Reads ``information_schema`` over a NEW safe
connection (local-Docker-only, read-only, lazy psycopg2) and produces a
``DatabaseSchema`` contract. Inert without a wired connection; never leaks
connection credentials in errors. The legacy
``SchemaManager._extract_postgres_metadata`` is intentionally left untouched.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.evaluation.postgres_adapter import SQLPostgresLocalDockerConnection
from app.schema.schema_contract import (
    ColumnSchema,
    DatabaseSchema,
    RelationshipSchema,
    RelationshipType,
    TableSchema,
)

SQL_POSTGRES_SCHEMA_ADAPTER_CONTRACT_VERSION = "sql_postgres_schema_adapter_contract_v1"


class SQLPostgresSchemaAdapterStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    EXECUTION_ERROR = "execution_error"
    EXTRACTED = "extracted"


@dataclass(frozen=True)
class SQLPostgresSchemaAdapterConfig:
    connect_timeout_seconds: float = 5.0
    statement_timeout_seconds: float = 5.0
    schema_name: str = "public"


@dataclass(frozen=True)
class SQLPostgresSchemaIntrospectionResult:
    version: str
    status: SQLPostgresSchemaAdapterStatus
    schema: Optional[DatabaseSchema] = None
    table_count: int = 0
    relationship_count: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0


def build_database_schema_from_introspection(
    *,
    database_name: Optional[str],
    tables: List[str],
    columns: Dict[str, List[Dict[str, Any]]],
    primary_keys: Dict[str, List[str]],
    foreign_keys: List[Dict[str, str]],
) -> DatabaseSchema:
    """Pure, deterministic assembly of a DatabaseSchema from raw introspection rows."""
    table_models: List[TableSchema] = []
    for table_name in sorted(tables):
        pk_cols = primary_keys.get(table_name, [])
        pk_set = set(pk_cols)
        col_rows = sorted(
            columns.get(table_name, []),
            key=lambda c: (c.get("ordinal_position") if c.get("ordinal_position") is not None else 0, c["name"]),
        )
        col_models = [
            ColumnSchema(
                name=c["name"],
                data_type=c.get("data_type"),
                nullable=c.get("nullable"),
                primary_key=c["name"] in pk_set,
                ordinal_position=c.get("ordinal_position"),
            )
            for c in col_rows
        ]
        table_models.append(
            TableSchema(
                name=table_name,
                columns=col_models,
                primary_key_columns=sorted(pk_cols),
            )
        )

    rels = [
        RelationshipSchema(
            source_table=fk["source_table"],
            source_column=fk["source_column"],
            target_table=fk["target_table"],
            target_column=fk["target_column"],
            relationship_type=RelationshipType.EXPLICIT,
        )
        for fk in sorted(
            foreign_keys,
            key=lambda f: (f["source_table"], f["source_column"], f["target_table"], f["target_column"]),
        )
    ]

    return DatabaseSchema(
        dialect="postgresql",
        database_name=database_name,
        tables=table_models,
        relationships=rels,
    )


def _sanitize_schema_error(exc: Exception) -> str:
    """Credential-free, deterministic error (never leaks host/user/password/driver text)."""
    pgcode = getattr(exc, "pgcode", None)
    if pgcode == "57014":  # query_canceled (statement_timeout)
        return "PostgreSQL introspection timed out (statement_timeout exceeded)."
    return f"PostgreSQL introspection failed ({type(exc).__name__})."


class SQLPostgresSchemaAdapterContract:
    def __init__(
        self,
        connection: Optional[SQLPostgresLocalDockerConnection] = None,
        config: Optional[SQLPostgresSchemaAdapterConfig] = None,
    ):
        self._connection = connection
        self._config = config or SQLPostgresSchemaAdapterConfig()

    def _result(self, status, *, schema=None, error=None, duration_ms=0.0):
        rel_count = len(schema.relationships) if schema is not None else 0
        tbl_count = len(schema.tables) if schema is not None else 0
        return SQLPostgresSchemaIntrospectionResult(
            version=SQL_POSTGRES_SCHEMA_ADAPTER_CONTRACT_VERSION,
            status=status,
            schema=schema,
            table_count=tbl_count,
            relationship_count=rel_count,
            error=error,
            duration_ms=duration_ms,
        )

    def introspect(self) -> SQLPostgresSchemaIntrospectionResult:
        if self._connection is None:
            return self._result(SQLPostgresSchemaAdapterStatus.NOT_IMPLEMENTED)

        try:
            import psycopg2  # noqa: WPS433 - lazy, runtime-only
            from psycopg2.extras import RealDictCursor
        except ImportError:
            return self._result(
                SQLPostgresSchemaAdapterStatus.EXECUTION_ERROR,
                error="PostgreSQL driver (psycopg2) is not available.",
            )

        conn = self._connection
        cfg = self._config
        stmt_ms = max(1, int(cfg.statement_timeout_seconds * 1000))
        connect_timeout_s = max(1, int(round(cfg.connect_timeout_seconds)))
        started = time.monotonic()
        db = None
        try:
            db = psycopg2.connect(
                host=conn.host, port=conn.port, dbname=conn.dbname,
                user=conn.user, password=conn.password,
                connect_timeout=connect_timeout_s,
                options=f"-c statement_timeout={stmt_ms} -c default_transaction_read_only=on",
            )
            db.set_session(readonly=True, autocommit=False)
            with db.cursor(cursor_factory=RealDictCursor) as cur:
                tables, columns, pks, fks = self._read_information_schema(cur, cfg.schema_name)
            db.rollback()
            schema = build_database_schema_from_introspection(
                database_name=conn.dbname,
                tables=tables, columns=columns, primary_keys=pks, foreign_keys=fks,
            )
            duration_ms = (time.monotonic() - started) * 1000.0
            return self._result(
                SQLPostgresSchemaAdapterStatus.EXTRACTED, schema=schema, duration_ms=duration_ms
            )
        except Exception as exc:  # noqa: BLE001 - must never leak connection details
            duration_ms = (time.monotonic() - started) * 1000.0
            return self._result(
                SQLPostgresSchemaAdapterStatus.EXECUTION_ERROR,
                error=_sanitize_schema_error(exc), duration_ms=duration_ms,
            )
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

    @staticmethod
    def _read_information_schema(cur, schema_name: str):
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """,
            (schema_name,),
        )
        tables = [r["table_name"] for r in cur.fetchall()]

        columns: Dict[str, List[Dict[str, Any]]] = {}
        cur.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns WHERE table_schema = %s
            """,
            (schema_name,),
        )
        for r in cur.fetchall():
            columns.setdefault(r["table_name"], []).append({
                "name": r["column_name"],
                "data_type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "ordinal_position": r["ordinal_position"],
            })

        pks: Dict[str, List[str]] = {}
        cur.execute(
            """
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
            """,
            (schema_name,),
        )
        for r in cur.fetchall():
            pks.setdefault(r["table_name"], []).append(r["column_name"])

        fks: List[Dict[str, str]] = []
        cur.execute(
            """
            SELECT
                tc.table_name       AS source_table,
                kcu.column_name     AS source_column,
                ref_kcu.table_name  AS target_table,
                ref_kcu.column_name AS target_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_name = tc.constraint_name
             AND rc.constraint_schema = tc.table_schema
            JOIN information_schema.key_column_usage ref_kcu
              ON ref_kcu.constraint_name = rc.unique_constraint_name
             AND ref_kcu.constraint_schema = rc.unique_constraint_schema
             AND ref_kcu.ordinal_position = kcu.position_in_unique_constraint
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
            """,
            (schema_name,),
        )
        for r in cur.fetchall():
            fks.append({
                "source_table": r["source_table"], "source_column": r["source_column"],
                "target_table": r["target_table"], "target_column": r["target_column"],
            })

        # Only tables that actually have columns produce a valid TableSchema.
        tables = [t for t in tables if columns.get(t)]
        return tables, columns, pks, fks
