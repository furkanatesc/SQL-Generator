import json
import os
import pytest
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_context_selector import select_schema_context
from app.schema.schema_prompt_serializer import serialize_selection_for_prompt

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "context_selection_golden_schema.json")
GOLDEN_CASES_PATH = os.path.join(FIXTURES_DIR, "context_selection_golden_cases.json")

def load_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture(scope="module")
def golden_schema():
    raw_schema = load_json(GOLDEN_SCHEMA_PATH)
    return from_legacy_schema(raw_schema, dialect="postgres")

@pytest.fixture(scope="module")
def golden_cases():
    return load_json(GOLDEN_CASES_PATH)

def extract_prompt_tables(prompt: str) -> set[str]:
    """
    Extracts tables listed in the serialized prompt under the 'Tables:' section.
    This ensures we check what the LLM actually sees, including intermediate join tables.
    """
    lines = prompt.splitlines()
    tables = set()
    in_tables_section = False
    for line in lines:
        if line.strip() == "Tables:":
            in_tables_section = True
            continue
        if line.strip() in ("Relationships:", "Join Paths:"):
            in_tables_section = False
            continue
            
        if in_tables_section:
            # Table names are printed directly as top-level lines without indentation
            # Columns are indented with '  -'
            if line and not line.startswith(" ") and not line.startswith("\t"):
                tables.add(line.strip())
                
    return tables

# --- Fixture Validation Tests ---

def test_golden_cases_have_unique_ids(golden_cases):
    ids = [case["id"] for case in golden_cases]
    assert len(ids) == len(set(ids)), "Golden cases must have unique IDs"

def test_golden_cases_reference_existing_tables(golden_schema, golden_cases):
    schema_table_names = {t.name for t in golden_schema.tables}
    for case in golden_cases:
        for t in case["required_tables"]:
            assert t in schema_table_names, f"Required table {t} in case {case['id']} not in schema"
        for t in case["forbidden_tables"]:
            assert t in schema_table_names, f"Forbidden table {t} in case {case['id']} not in schema"

def test_golden_cases_reference_existing_relationships(golden_schema, golden_cases):
    # Create a set of (source, source_col, target, target_col) tuples
    edges = {
        (rel.source_table, rel.source_column, rel.target_table, rel.target_column) 
        for rel in golden_schema.relationships
    }

    for case in golden_cases:
        for edge in case["required_join_edges"]:
            source_table, source_col, target_table, target_col = edge
            assert tuple(edge) in edges, \
                f"Relationship {source_table}.{source_col} -> {target_table}.{target_col} in case {case['id']} not in schema"

# --- Eval Tests ---

def test_context_selection_golden_cases_pass(golden_schema, golden_cases):
    """
    Tests required table recall and max boundary limits.
    """
    for case in golden_cases:
        selection = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])
        prompt_context = serialize_selection_for_prompt(golden_schema, selection)
        prompt_tables = extract_prompt_tables(prompt_context)
        
        # 1. Required table recall (required_tables ⊆ prompt_context_tables)
        for req_table in case["required_tables"]:
            assert req_table in prompt_tables, \
                f"Case '{case['id']}': Required table '{req_table}' missing from prompt context. Found: {prompt_tables}"
                
        # 2. Bounded output
        assert len(prompt_tables) <= case["max_selected_tables"], \
            f"Case '{case['id']}': Expected max {case['max_selected_tables']} tables, but got {len(prompt_tables)}"
            
        # 3. Fallback expectation
        assert selection.fallback_used is case["expect_fallback"], \
            f"Case '{case['id']}': Expected fallback={case['expect_fallback']}, got {selection.fallback_used}"

def test_context_selection_forbidden_tables_are_excluded(golden_schema, golden_cases):
    """
    Tests that forbidden tables are omitted from prompt context.
    """
    for case in golden_cases:
        selection = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])
        prompt_context = serialize_selection_for_prompt(golden_schema, selection)
        prompt_tables = extract_prompt_tables(prompt_context)
    
        # forbidden_tables ∩ prompt_context_tables == ∅
        for forbidden in case["forbidden_tables"]:
            assert forbidden not in prompt_tables, \
                f"Case '{case['id']}': Forbidden table '{forbidden}' found in prompt context."

def test_context_selection_required_join_edges_are_serialized(golden_schema, golden_cases):
    """
    Validates the exact string representation of the join paths in the serialized prompt.
    """
    for case in golden_cases:
        selection = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])
        prompt_context = serialize_selection_for_prompt(golden_schema, selection)
        
        for edge in case["required_join_edges"]:
            source_table, source_col, target_table, target_col = edge
            
            # The prompt string format depends on explicit vs implicit. 
            # In golden schema, they are explicit relationships.
            # Example format:  - [EXPLICIT] payments.order_id -> orders.id
            # We search for the exact edge string substring.
            expected_substring = f"{source_table}.{source_col} -> {target_table}.{target_col}"
            
            assert expected_substring in prompt_context, \
                f"Case '{case['id']}': Expected join edge '{expected_substring}' not found in prompt context."

def test_context_selection_fallback_case_is_bounded(golden_schema, golden_cases):
    """
    Specifically asserts fallback mechanism caps table outputs appropriately.
    """
    fallback_cases = [c for c in golden_cases if c["expect_fallback"]]
    for case in fallback_cases:
        selection = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])
        prompt_context = serialize_selection_for_prompt(golden_schema, selection)
        prompt_tables = extract_prompt_tables(prompt_context)
        
        assert selection.fallback_used is True
        assert len(prompt_tables) <= case["max_selected_tables"]

def test_context_selection_golden_cases_are_deterministic(golden_schema, golden_cases):
    """
    Asserts identical inputs produce identical selected focus tables and identical prompt text outputs across multiple runs.
    """
    for case in golden_cases:
        selection_1 = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])
        selection_2 = select_schema_context(golden_schema, case["question"], max_tables=case["max_selected_tables"])

        assert selection_1.focus_tables == selection_2.focus_tables, \
            f"Case '{case['id']}': focus_tables nondeterministic"
            
        prompt_1 = serialize_selection_for_prompt(golden_schema, selection_1)
        prompt_2 = serialize_selection_for_prompt(golden_schema, selection_2)
        
        assert prompt_1 == prompt_2, \
            f"Case '{case['id']}': prompt serialization nondeterministic"
