"""Sprint 29.0 — schema introspection integration tests (seeded schema).

Skipped safely when no local Docker PostgreSQL is reachable; runs in CI and
locally via `docker compose up -d postgres`.
"""
import json
import pytest

from app.evaluation.postgres_connection_resolver import resolve_local_docker_connection
from app.evaluation.postgres_schema_adapter import (
    SQLPostgresSchemaAdapterContract,
    SQLPostgresSchemaAdapterStatus,
)
from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterConfig,
    SQLPostgresAdapterContract,
    SQLPostgresAdapterExecutionRequest,
    SQLPostgresAdapterStatus,
)
from app.schema.schema_contract import RelationshipType

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _local_docker_postgres_available():
    try:
        import psycopg2
    except ImportError:
        return False
    conn = resolve_local_docker_connection()
    if conn is None:
        return False
    try:
        db = psycopg2.connect(
            host=conn.host, port=conn.port, dbname=conn.dbname,
            user=conn.user, password=conn.password, connect_timeout=2,
        )
        db.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def connection():
    if not _local_docker_postgres_available():
        pytest.skip("local Docker PostgreSQL not available")
    return resolve_local_docker_connection()


def test_introspection_extracts_seeded_tables(connection):
    result = SQLPostgresSchemaAdapterContract(connection=connection).introspect()
    assert result.status == SQLPostgresSchemaAdapterStatus.EXTRACTED
    names = {t.name for t in result.schema.tables}
    assert {"customers", "orders", "order_items"}.issubset(names)


def test_introspection_primary_keys_and_types(connection):
    schema = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    customers = next(t for t in schema.tables if t.name == "customers")
    assert customers.primary_key_columns == ["id"]
    id_col = next(c for c in customers.columns if c.name == "id")
    assert id_col.primary_key is True
    assert id_col.data_type == "integer"


def test_introspection_foreign_keys_direction_and_type(connection):
    schema = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    edges = {(r.source_table, r.source_column, r.target_table, r.target_column): r for r in schema.relationships}
    assert ("orders", "customer_id", "customers", "id") in edges
    assert ("order_items", "order_id", "orders", "id") in edges
    for r in schema.relationships:
        assert r.relationship_type == RelationshipType.EXPLICIT


def test_introspection_composite_foreign_key_pairs_correctly(connection):
    schema = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    edges = {
        (r.source_table, r.source_column, r.target_table, r.target_column)
        for r in schema.relationships
        if r.source_table == "variant_stock"
    }
    assert ("variant_stock", "product_id", "product_variants", "product_id") in edges
    assert ("variant_stock", "sku", "product_variants", "sku") in edges
    # No cross-product mispairings:
    assert ("variant_stock", "product_id", "product_variants", "sku") not in edges
    assert ("variant_stock", "sku", "product_variants", "product_id") not in edges
    assert len(edges) == 2


def test_introspection_is_deterministic(connection):
    a = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    b = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    assert a.model_dump() == b.model_dump()


def test_introspection_does_not_leak_credentials(connection):
    # Serialize only structural content (exclude database_name, which legitimately
    # is "sqlgen_test"); assert no host/password material leaks into the schema.
    schema = SQLPostgresSchemaAdapterContract(connection=connection).introspect().schema
    structural = {
        "tables": [t.model_dump() for t in schema.tables],
        "relationships": [r.model_dump() for r in schema.relationships],
    }
    serialized = json.dumps(structural, default=str)
    assert "localhost" not in serialized
    assert "127.0.0.1" not in serialized
    assert "password" not in serialized.lower()


def test_real_join_over_seeded_schema(connection):
    adapter = SQLPostgresAdapterContract(connection=connection)
    sql = (
        "SELECT c.name, oi.product_name, oi.qty "
        "FROM customers c "
        "JOIN orders o ON o.customer_id = c.id "
        "JOIN order_items oi ON oi.order_id = o.id "
        "WHERE c.id = 1 ORDER BY oi.id"
    )
    req = SQLPostgresAdapterExecutionRequest(
        case_id="join", sql=sql, dialect="postgresql",
        config=SQLPostgresAdapterConfig(),
    )
    result = adapter.execute(req)
    assert result.status == SQLPostgresAdapterStatus.EXECUTED
    assert result.rows == (
        ("Ada Lovelace", "Widget", 2),
        ("Ada Lovelace", "Gadget", 1),
        ("Ada Lovelace", "Widget", 1),
    )
