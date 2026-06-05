import pytest
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
    )

    assert schema.tables[0].name == "users"
    assert schema.tables[0].columns[0].primary_key is True

def test_table_rejects_duplicate_column_names():
    with pytest.raises(ValueError, match="Duplicate column names are not allowed"):
        TableSchema(
            name="users",
            columns=[
                ColumnSchema(name="id"),
                ColumnSchema(name="id"),
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
