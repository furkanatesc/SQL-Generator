import json
import os
import pytest
import sys

from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, SchemaGraph
from app.schema.schema_summary import (
    SCHEMA_SUMMARY_VERSION,
    summarize_database_schema,
    summarize_table,
    summarize_column,
    summarize_relationship,
    ColumnSummary,
    RelationshipSummary,
    TableSummary
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "schema", "context_selection_golden_schema.json")


def load_golden_schema() -> DatabaseSchema:
    with open(GOLDEN_SCHEMA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return from_legacy_schema(raw, dialect="sqlite")


def test_schema_summary_is_deterministic():
    """
    Test 1 — deterministic output
    Verifies that calling summarize_database_schema multiple times produces identical byte-for-byte outputs.
    """
    schema = load_golden_schema()
    first = summarize_database_schema(schema)
    second = summarize_database_schema(schema)
    
    assert first == second
    for f_tab, s_tab in zip(first, second):
        assert f_tab.summary_text == s_tab.summary_text


def test_stable_ordering():
    """
    Test 2 — stable ordering
    Verifies that output summaries are sorted alphabetically by table_name,
    columns by column_name, relationships by source_table, source_column, target_table, target_column,
    and tags alphabetically.
    """
    # Create a deliberately unordered mock schema
    unordered_schema = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(
                name="payments",
                columns=[
                    ColumnSchema(name="amount", data_type="DECIMAL"),
                    ColumnSchema(name="id", data_type="INTEGER", primary_key=True),
                ]
            ),
            TableSchema(
                name="customers",
                columns=[
                    ColumnSchema(name="name", data_type="VARCHAR"),
                    ColumnSchema(name="id", data_type="INTEGER", primary_key=True),
                    ColumnSchema(name="email", data_type="VARCHAR", raw={"semantic_tags": ["pii", "auth_id"]}),
                ]
            ),
            TableSchema(
                name="orders",
                columns=[
                    ColumnSchema(name="id", data_type="INTEGER", primary_key=True),
                    ColumnSchema(name="customer_id", data_type="INTEGER"),
                ]
            )
        ],
        relationships=[
            RelationshipSchema(
                source_table="payments",
                source_column="id",
                target_table="orders",
                target_column="id"
            ),
            RelationshipSchema(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id"
            )
        ]
    )

    summaries = summarize_database_schema(unordered_schema)

    # 1. Tables must be sorted by table_name
    table_names = [s.table_name for s in summaries]
    assert table_names == ["customers", "orders", "payments"]

    # 2. Columns must be sorted by column_name in TableSummary
    customers_summary = next(s for s in summaries if s.table_name == "customers")
    column_names = [c.column_name for c in customers_summary.columns]
    assert column_names == ["email", "id", "name"]

    # 3. Tags must be sorted alphabetically
    email_summary = next(c for c in customers_summary.columns if c.column_name == "email")
    assert email_summary.semantic_tags == ("auth_id", "pii")

    # 4. Relationships must be sorted by source_table, source_column, target_table, target_column
    # Let's inspect the order inside a TableSummary that has multiple relationships
    # The orders table has relationships with both customers and payments
    orders_summary = next(s for s in summaries if s.table_name == "orders")
    rel_signatures = [
        f"{r.source_table}.{r.source_column} -> {r.target_table}.{r.target_column}"
        for r in orders_summary.relationships
    ]
    # Sorted order of source_table:
    # 1. orders.customer_id -> customers.id (source: orders)
    # 2. payments.id -> orders.id (source: payments)
    assert rel_signatures == [
        "orders.customer_id -> customers.id",
        "payments.id -> orders.id"
    ]


def test_table_summary_contains_columns():
    """
    Test 3 — table summary contains columns
    Verifies that the generated summary_text matches the exact expected layout.
    """
    schema = load_golden_schema()
    summaries = summarize_database_schema(schema)
    customers = next(s for s in summaries if s.table_name == "customers")

    expected_summary = f"""TABLE customers
COLUMNS:
- email VARCHAR
- id INTEGER pk
- name VARCHAR
RELATIONSHIPS:
- orders.customer_id -> customers.id explicit
- support_tickets.customer_id -> customers.id explicit
VERSION: {SCHEMA_SUMMARY_VERSION}"""

    assert customers.summary_text == expected_summary


def test_relationship_direction_preserved():
    """
    Test 4 — relationship direction preserved
    Verifies that relationship directions (source/child -> target/parent) are preserved
    under both source and target table summaries.
    """
    schema = load_golden_schema()
    summaries = summarize_database_schema(schema)
    
    customers = next(s for s in summaries if s.table_name == "customers")
    orders = next(s for s in summaries if s.table_name == "orders")

    # The direction must remain orders -> customers in both summaries
    assert "orders.customer_id -> customers.id" in customers.summary_text
    assert "customers.id -> orders.customer_id" not in customers.summary_text

    assert "orders.customer_id -> customers.id" in orders.summary_text
    assert "customers.id -> orders.customer_id" not in orders.summary_text


def test_summary_version_present():
    """
    Test 5 — summary version present
    Verifies that summary_version field is present and version text exists in output.
    """
    schema = load_golden_schema()
    summaries = summarize_database_schema(schema)
    
    for summary in summaries:
        assert summary.summary_version == SCHEMA_SUMMARY_VERSION
        assert f"VERSION: {SCHEMA_SUMMARY_VERSION}" in summary.summary_text


def test_no_network_or_vector_dependency():
    """
    Test 6 — no network / no vector dependency
    Verifies that no vector DB or LLM-related libraries are imported or loaded.
    """
    forbidden_modules = [
        "qdrant_client",
        "openai"
    ]
    for mod in forbidden_modules:
        assert mod not in sys.modules, f"Forbidden module '{mod}' was imported or loaded!"


def test_column_and_relationship_individual_summaries():
    """
    Verifies the standalone summary text and properties for ColumnSummary and RelationshipSummary.
    """
    col = ColumnSummary(
        table_name="customers",
        column_name="email",
        data_type="VARCHAR",
        nullable=False,
        semantic_tags=("email", "pii")
    )
    assert col.summary_version == SCHEMA_SUMMARY_VERSION
    expected_col_text = f"""COLUMN customers.email
TYPE: VARCHAR
NULLABLE: false
TAGS: email,pii
VERSION: {SCHEMA_SUMMARY_VERSION}"""
    assert col.summary_text == expected_col_text

    rel = RelationshipSummary(
        source_table="orders",
        source_column="customer_id",
        target_table="customers",
        target_column="id",
        relationship_type="explicit",
        confidence=1.0
    )
    assert rel.summary_version == SCHEMA_SUMMARY_VERSION
    expected_rel_text = f"""RELATIONSHIP orders.customer_id -> customers.id
TYPE: explicit
CONFIDENCE: 1.0
VERSION: {SCHEMA_SUMMARY_VERSION}"""
    assert rel.summary_text == expected_rel_text
