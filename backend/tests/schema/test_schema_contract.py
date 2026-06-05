import pytest
from pydantic import ValidationError
from app.schema.schema_contract import (
    DatabaseSchema,
    TableSchema,
    ColumnSchema,
    RelationshipSchema,
    SchemaGraph
)

def test_valid_minimal_database_schema():
    schema = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(
                name="users",
                columns=[
                    ColumnSchema(name="id", data_type="INTEGER", primary_key=True),
                    ColumnSchema(name="email", data_type="TEXT"),
                ],
                primary_key_columns=["id"],
            )
        ],
        graph=SchemaGraph(nodes=["users"], edges=[])
    )

    assert schema.tables[0].name == "users"
    assert schema.tables[0].columns[0].primary_key is True

def test_table_rejects_duplicate_column_names():
    with pytest.raises(ValueError, match="Duplicate column names detected"):
        TableSchema(
            name="users",
            columns=[
                ColumnSchema(name="id"),
                ColumnSchema(name="ID"),
            ],
        )

def test_table_rejects_empty_name():
    with pytest.raises(ValueError, match="Table name cannot be empty"):
        TableSchema(
            name="   ",
            columns=[ColumnSchema(name="id")]
        )

def test_column_rejects_empty_name():
    with pytest.raises(ValueError, match="Column name cannot be empty"):
        ColumnSchema(name="")

def test_table_requires_at_least_one_column():
    with pytest.raises(ValueError, match="Table must have at least one column"):
        TableSchema(name="users", columns=[])

def test_relationship_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
        RelationshipSchema(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="implicit",
            confidence=1.5,
        )

def test_relationship_rejects_empty_names():
    with pytest.raises(ValueError, match="Source and target table names cannot be empty"):
        RelationshipSchema(
            source_table="",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
    with pytest.raises(ValueError, match="Source and target column names cannot be empty"):
        RelationshipSchema(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="  ",
        )

def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        ColumnSchema(name="id", unknown_field=True)

    with pytest.raises(ValidationError):
        TableSchema(name="users", columns=[ColumnSchema(name="id")], foo="bar")

    with pytest.raises(ValidationError):
        RelationshipSchema(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            unexpected="x"
        )

def test_graph_rejects_empty_or_duplicate_nodes():
    with pytest.raises(ValueError, match="Graph nodes cannot be empty strings"):
        SchemaGraph(nodes=["users", ""], edges=[])
        
    with pytest.raises(ValueError, match="Graph contains duplicate nodes"):
        SchemaGraph(nodes=["users", "users"], edges=[])

def test_graph_edges_must_reference_existing_nodes():
    with pytest.raises(ValueError, match="target_table references unknown node: 'unknown'"):
        SchemaGraph(
            nodes=["users"],
            edges=[
                RelationshipSchema(
                    source_table="users",
                    source_column="id",
                    target_table="unknown",
                    target_column="id"
                )
            ]
        )

def test_database_schema_validates_consistency():
    # Duplicate table
    with pytest.raises(ValueError, match="Duplicate table names detected"):
        DatabaseSchema(
            dialect="sqlite",
            tables=[
                TableSchema(name="users", columns=[ColumnSchema(name="id")]),
                TableSchema(name="users", columns=[ColumnSchema(name="email")]),
            ]
        )
        
    # Graph nodes vs table mismatch
    with pytest.raises(ValueError, match="Graph nodes and table names do not match"):
        DatabaseSchema(
            dialect="sqlite",
            tables=[TableSchema(name="users", columns=[ColumnSchema(name="id")])],
            graph=SchemaGraph(nodes=["users", "orders"], edges=[])
        )
        
    # Edge references unknown table
    with pytest.raises(ValueError, match="Relationship source_table references unknown table: 'orders'"):
        DatabaseSchema(
            dialect="sqlite",
            tables=[TableSchema(name="users", columns=[ColumnSchema(name="id")])],
            relationships=[
                RelationshipSchema(
                    source_table="orders",
                    source_column="user_id",
                    target_table="users",
                    target_column="id",
                )
            ]
        )
        
    # Edge references unknown column
    with pytest.raises(ValueError, match="Relationship source_column 'invalid_col' not found in table 'users'"):
        DatabaseSchema(
            dialect="sqlite",
            tables=[TableSchema(name="users", columns=[ColumnSchema(name="id")])],
            relationships=[
                RelationshipSchema(
                    source_table="users",
                    source_column="invalid_col",
                    target_table="users",
                    target_column="id",
                )
            ]
        )
