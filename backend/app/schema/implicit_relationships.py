import difflib
from typing import Any
from .schema_contract import DatabaseSchema, RelationshipSchema, RelationshipType
from .schema_adapter import from_legacy_schema

GENERIC_RELATIONSHIP_COLUMN_NAMES = {
    "id", "name", "type", "status", "description", 
    "created_at", "updated_at", "created_by", "updated_by", 
    "active", "is_active", "date", "value", "code", "seq", 
    "remark", "notes", "title", "email"
}

def is_generic_column(col_name: str) -> bool:
    return col_name.lower() in GENERIC_RELATIONSHIP_COLUMN_NAMES

def detect_implicit_relationships(schema: dict | DatabaseSchema) -> list[RelationshipSchema]:
    """
    Detects implicit relationships heuristically while rejecting generic matches.
    """
    if isinstance(schema, dict):
        # We need a dialect for the adapter; 'postgres' is a safe default for raw tests
        db_schema = from_legacy_schema(schema, dialect="postgres")
    else:
        db_schema = schema

    relationships = []
    tables = db_schema.tables
    
    # Track existing explicit edges to prevent modifying/duplicating them
    explicit_edges = set()
    for rel in db_schema.relationships:
        if rel.relationship_type == RelationshipType.EXPLICIT:
            explicit_edges.add((rel.source_table, rel.source_column, rel.target_table, rel.target_column))

    # Helper to check if an edge is already explicitly defined
    def is_explicit(src_table, src_col, tgt_table, tgt_col):
        return (src_table, src_col, tgt_table, tgt_col) in explicit_edges

    for src_table in tables:
        for tgt_table in tables:
            if src_table.name == tgt_table.name:
                continue

            for src_col in src_table.columns:
                src_col_lower = src_col.name.lower()
                
                # Check for table_id singular match pattern
                # e.g. 'users' -> 'user_id'
                tgt_singular = tgt_table.name.lower().rstrip('s')
                expected_fk_name = f"{tgt_singular}_id"

                if src_col_lower == expected_fk_name:
                    # Look for an 'id' column in the target table
                    for tgt_col in tgt_table.columns:
                        if tgt_col.name.lower() == "id":
                            if not is_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
                                relationships.append(RelationshipSchema(
                                    source_table=src_table.name,
                                    source_column=src_col.name,
                                    target_table=tgt_table.name,
                                    target_column=tgt_col.name,
                                    relationship_type=RelationshipType.IMPLICIT,
                                    confidence=0.90,
                                    reason="singular_table_id_pattern",
                                    raw={"rule": "singular_table_id_pattern", "matched_prefix": tgt_singular}
                                ))
                            break # Move to next source column
                
                # Check exact column name match (only if not generic)
                elif not is_generic_column(src_col_lower):
                    for tgt_col in tgt_table.columns:
                        tgt_col_lower = tgt_col.name.lower()
                        if src_col_lower == tgt_col_lower:
                            # It's an exact match on a non-generic column
                            if not is_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
                                relationships.append(RelationshipSchema(
                                    source_table=src_table.name,
                                    source_column=src_col.name,
                                    target_table=tgt_table.name,
                                    target_column=tgt_col.name,
                                    relationship_type=RelationshipType.IMPLICIT,
                                    confidence=0.60,
                                    reason="exact_non_generic_column_match",
                                    raw={"rule": "exact_column_match", "column": src_col_lower}
                                ))
                            break # Move to next source column

                # Check fuzzy match
                for tgt_col in tgt_table.columns:
                    tgt_col_lower = tgt_col.name.lower()
                    if is_generic_column(src_col_lower) or is_generic_column(tgt_col_lower):
                        continue # Generic columns do not participate in fuzzy matching
                    
                    if src_col_lower == tgt_col_lower or src_col_lower == expected_fk_name:
                        continue # Already handled above

                    # Check fuzzy string matching using difflib
                    ratio = difflib.SequenceMatcher(None, src_col_lower, tgt_col_lower).ratio()
                    
                    if ratio >= 0.90:
                        confidence = 0.75
                    elif ratio >= 0.85:
                        confidence = 0.65
                    else:
                        continue

                    if not is_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
                        relationships.append(RelationshipSchema(
                            source_table=src_table.name,
                            source_column=src_col.name,
                            target_table=tgt_table.name,
                            target_column=tgt_col.name,
                            relationship_type=RelationshipType.IMPLICIT_FUZZY,
                            confidence=confidence,
                            reason="fuzzy_column_match",
                            raw={"rule": "fuzzy_match", "ratio": ratio}
                        ))

    return relationships
