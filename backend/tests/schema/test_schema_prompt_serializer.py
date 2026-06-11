import pytest
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, RelationshipType
from app.schema.schema_prompt_serializer import serialize_schema_for_prompt

@pytest.fixture
def relationship_schema():
    return DatabaseSchema(
        dialect="postgres",
        tables=[
            TableSchema(
                name="users",
                columns=[ColumnSchema(name="id", primary_key=True)]
            ),
            TableSchema(
                name="profiles",
                columns=[ColumnSchema(name="user_id"), ColumnSchema(name="id", primary_key=True)]
            ),
            TableSchema(
                name="logs",
                columns=[ColumnSchema(name="user_id"), ColumnSchema(name="id", primary_key=True)]
            ),
            TableSchema(
                name="sessions",
                columns=[ColumnSchema(name="user_id"), ColumnSchema(name="id", primary_key=True)]
            )
        ],
        relationships=[
            RelationshipSchema(
                source_table="profiles", source_column="user_id",
                target_table="users", target_column="id",
                relationship_type=RelationshipType.EXPLICIT
            ),
            RelationshipSchema(
                source_table="logs", source_column="user_id",
                target_table="users", target_column="id",
                relationship_type=RelationshipType.IMPLICIT_FUZZY,
                confidence=0.4,
                reason="fuzzy column match"
            ),
            RelationshipSchema(
                source_table="sessions", source_column="user_id",
                target_table="users", target_column="id",
                relationship_type=RelationshipType.DISABLED
            )
        ]
    )

def test_prompt_excludes_implicit_fuzzy_relationships(relationship_schema):
    prompt = serialize_schema_for_prompt(
        relationship_schema,
        focus_tables=["users", "profiles", "logs", "sessions"],
        max_tables=10
    )
    
    assert "profiles.user_id -> users.id" in prompt
    assert "logs.user_id -> users.id" not in prompt
    assert "fuzzy" not in prompt

def test_prompt_excludes_disabled_relationships(relationship_schema):
    prompt = serialize_schema_for_prompt(
        relationship_schema,
        focus_tables=["users", "profiles", "logs", "sessions"],
        max_tables=10
    )
    
    assert "sessions.user_id -> users.id" not in prompt
    assert "disabled" not in prompt.lower()
