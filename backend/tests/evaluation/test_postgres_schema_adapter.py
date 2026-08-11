import sys
import pytest

from app.evaluation.postgres_schema_adapter import (
    SQL_POSTGRES_SCHEMA_ADAPTER_CONTRACT_VERSION,
    SQLPostgresSchemaAdapterConfig,
    SQLPostgresSchemaAdapterContract,
    SQLPostgresSchemaAdapterStatus,
    build_database_schema_from_introspection,
)
from app.evaluation.postgres_adapter import SQLPostgresLocalDockerConnection
from app.schema.schema_contract import DatabaseSchema, RelationshipType


def _sample_introspection():
    return dict(
        database_name="sqlgen_test",
        tables=["orders", "customers"],  # deliberately unsorted
        columns={
            "customers": [
                {"name": "id", "data_type": "integer", "nullable": False, "ordinal_position": 1},
                {"name": "name", "data_type": "text", "nullable": False, "ordinal_position": 2},
            ],
            "orders": [
                {"name": "id", "data_type": "integer", "nullable": False, "ordinal_position": 1},
                {"name": "customer_id", "data_type": "integer", "nullable": False, "ordinal_position": 2},
            ],
        },
        primary_keys={"customers": ["id"], "orders": ["id"]},
        foreign_keys=[
            {"source_table": "orders", "source_column": "customer_id",
             "target_table": "customers", "target_column": "id"},
        ],
    )


def test_builder_produces_valid_database_schema():
    schema = build_database_schema_from_introspection(**_sample_introspection())
    assert isinstance(schema, DatabaseSchema)
    assert schema.dialect == "postgresql"
    assert schema.database_name == "sqlgen_test"
    assert [t.name for t in schema.tables] == ["customers", "orders"]  # sorted
    customers = next(t for t in schema.tables if t.name == "customers")
    assert customers.primary_key_columns == ["id"]
    id_col = next(c for c in customers.columns if c.name == "id")
    assert id_col.primary_key is True
    assert id_col.data_type == "integer"
    assert id_col.nullable is False


def test_builder_relationship_direction_and_type():
    schema = build_database_schema_from_introspection(**_sample_introspection())
    assert len(schema.relationships) == 1
    rel = schema.relationships[0]
    assert rel.source_table == "orders" and rel.source_column == "customer_id"
    assert rel.target_table == "customers" and rel.target_column == "id"
    assert rel.relationship_type == RelationshipType.EXPLICIT


def test_builder_is_deterministic():
    a = build_database_schema_from_introspection(**_sample_introspection())
    b = build_database_schema_from_introspection(**_sample_introspection())
    assert a.model_dump() == b.model_dump()


def test_version_constant():
    assert SQL_POSTGRES_SCHEMA_ADAPTER_CONTRACT_VERSION == "sql_postgres_schema_adapter_contract_v1"


def test_introspect_without_connection_is_inert():
    adapter = SQLPostgresSchemaAdapterContract(connection=None)
    result = adapter.introspect()
    assert result.status == SQLPostgresSchemaAdapterStatus.NOT_IMPLEMENTED
    assert result.schema is None
    assert result.table_count == 0


def test_introspect_reports_missing_driver(monkeypatch):
    # Simulate psycopg2 not installed: importing it raises ImportError.
    monkeypatch.setitem(sys.modules, "psycopg2", None)
    conn = SQLPostgresLocalDockerConnection(host="localhost", port=5432, dbname="d", user="u")
    adapter = SQLPostgresSchemaAdapterContract(connection=conn)
    result = adapter.introspect()
    assert result.status == SQLPostgresSchemaAdapterStatus.EXECUTION_ERROR
    assert "psycopg2" in (result.error or "")


def test_module_import_is_driver_free():
    # The module must import without psycopg2 loaded (lazy import contract).
    import inspect
    import app.evaluation.postgres_schema_adapter as mod
    src = inspect.getsource(mod)
    # No top-level psycopg2 import: the only occurrence sits inside a function body.
    assert "import psycopg2" in src  # it IS used, but lazily
    top_level = [ln for ln in src.splitlines() if ln.startswith("import psycopg2") or ln.startswith("from psycopg2")]
    assert top_level == []
