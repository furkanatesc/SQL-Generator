import pytest
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, RelationshipType, SchemaGraph
from app.schema.schema_context_selector import SchemaContextSelection, SelectedTable
from app.schema.prompt_serializer import serialize_schema_for_prompt

@pytest.fixture
def sample_schema():
    rels = [
        RelationshipSchema(source_table="b", source_column="a_id", target_table="a", target_column="id", relationship_type=RelationshipType.EXPLICIT),
        RelationshipSchema(source_table="c", source_column="b_id", target_table="b", target_column="id", relationship_type=RelationshipType.IMPLICIT, confidence=0.8),
        RelationshipSchema(source_table="d", source_column="id", target_table="a", target_column="id", relationship_type=RelationshipType.IMPLICIT_FUZZY),
        RelationshipSchema(source_table="c", source_column="id", target_table="a", target_column="id", relationship_type=RelationshipType.DISABLED)
    ]
    return DatabaseSchema(
        dialect="postgres",
        tables=[
            TableSchema(name="a", columns=[ColumnSchema(name="id", primary_key=True)]),
            TableSchema(name="b", columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="a_id")]),
            TableSchema(name="c", columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="b_id")]),
            TableSchema(name="d", columns=[ColumnSchema(name="id", primary_key=True)]),
        ],
        relationships=rels,
        graph=SchemaGraph(nodes=["a", "b", "c", "d"], edges=rels)
    )

def test_prompt_serializer_filters_relationships(sample_schema):
    selection = SchemaContextSelection(
        selected_tables=[
            SelectedTable(table_name="a", score=1.0, reasons=[]),
            SelectedTable(table_name="b", score=1.0, reasons=[]),
            SelectedTable(table_name="c", score=1.0, reasons=[]),
            SelectedTable(table_name="d", score=1.0, reasons=[])
        ],
        focus_tables=["a", "b", "c", "d"],
        join_paths=[],
        fallback_used=False,
        fallback_strategy=None
    )
    
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    # Explicit should be included
    assert "b.a_id -> a.id [explicit]" in prompt
    # Implicit should be included with confidence
    assert "c.b_id -> b.id [implicit, confidence: 0.8]" in prompt
    
    # Implicit fuzzy should be EXCLUDED
    assert "d.id -> a.id" not in prompt
    assert "implicit_fuzzy" not in prompt
    
    # Disabled should be EXCLUDED
    assert "c.id -> a.id" not in prompt
    assert "disabled" not in prompt

def test_prompt_serializer_includes_join_path_tables_and_edges(sample_schema):
    from app.schema.graph_traversal import JoinPathCandidate, JoinPathEdge
    
    # Suppose we only select 'a' and 'c'
    selection = SchemaContextSelection(
        selected_tables=[
            SelectedTable(table_name="a", score=1.0, reasons=[]),
            SelectedTable(table_name="c", score=1.0, reasons=[]),
        ],
        focus_tables=["a", "c"],
        join_paths=[
            JoinPathCandidate(
                tables=["a", "b", "c"],
                edges=[
                    JoinPathEdge(
                        from_table="b", from_column="a_id",
                        to_table="a", to_column="id",
                        relationship_source_table="b", relationship_source_column="a_id",
                        relationship_target_table="a", relationship_target_column="id",
                        relationship_type=RelationshipType.EXPLICIT
                    ),
                    JoinPathEdge(
                        from_table="c", from_column="b_id",
                        to_table="b", to_column="id",
                        relationship_source_table="c", relationship_source_column="b_id",
                        relationship_target_table="b", relationship_target_column="id",
                        relationship_type=RelationshipType.IMPLICIT
                    )
                ],
                score=1.0,
                min_relationship_priority=1,
                min_confidence=1.0,
                path_length=2
            )
        ],
        fallback_used=False,
        fallback_strategy=None
    )
    
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    # 1. 'b' should be printed in the TABLES section even though not in selected_tables
    assert "TABLE a" in prompt
    assert "TABLE b" in prompt
    assert "TABLE c" in prompt
    assert "TABLE d" not in prompt
    
    # 2. Join Path should be printed with full edge details
    assert "JOIN PATH: a -> b -> c" in prompt
    assert "b.a_id -> a.id [explicit]" in prompt
    assert "c.b_id -> b.id [implicit]" in prompt
