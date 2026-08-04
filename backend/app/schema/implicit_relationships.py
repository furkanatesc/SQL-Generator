import difflib
from typing import Any
from .schema_contract import DatabaseSchema, RelationshipSchema, RelationshipType
from .schema_adapter import from_legacy_schema

GENERIC_RELATIONSHIP_COLUMN_NAMES = {
    "id", "name", "type", "status", "description", 
    "created_at", "updated_at", "created_by", "updated_by", 
    "active", "is_active", "date", "value", "code", "seq", 
    "remark", "notes", "title", "email", "eposta"
}

def is_generic_column(col_name: str | None) -> bool:
    if not col_name:
        return False
    return col_name.lower() in GENERIC_RELATIONSHIP_COLUMN_NAMES

def get_singular(t_name: str) -> str:
    t = t_name.lower()
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith("es") and not t.endswith("ss") and not t.endswith("ch") and not t.endswith("sh"):
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t

def detect_implicit_relationships(schema: dict | DatabaseSchema, *, probe=None) -> list[RelationshipSchema]:
    """
    Detects implicit relationships heuristically while rejecting generic matches.
    """
    if isinstance(schema, dict):
        db_schema = from_legacy_schema(schema, dialect="unknown")
    else:
        db_schema = schema

    relationships = []
    tables = db_schema.tables
    
    # Track existing explicit edges to prevent modifying/duplicating them bidirectionally
    explicit_edges = set()
    for rel in db_schema.relationships:
        if rel.relationship_type == RelationshipType.EXPLICIT:
            explicit_edges.add(frozenset({
                (rel.source_table, rel.source_column),
                (rel.target_table, rel.target_column)
            }))

    # Track seen edges for the current detection session to prevent bidirectional duplicates
    seen_edges = set()

    def is_seen_or_explicit(src_table, src_col, tgt_table, tgt_col) -> bool:
        canonical = frozenset({
            (src_table, src_col),
            (tgt_table, tgt_col)
        })
        if canonical in explicit_edges or canonical in seen_edges:
            return True
        seen_edges.add(canonical)
        return False

    # Inverted index for singular prefix lookups
    singular_to_table = {}
    for t in tables:
        t_lower = t.name.lower()
        t_singular = get_singular(t.name)
        singular_to_table[t_singular] = t.name
        if t_lower not in singular_to_table:
            singular_to_table[t_lower] = t.name

    for src_table in tables:
        for tgt_table in tables:
            if src_table.name == tgt_table.name:
                continue
            if probe is not None:
                probe.incr("pair_iteration")

            for src_col in src_table.columns:
                src_col_lower = src_col.name.lower()
                
                # Try to extract a prefix from _id suffix
                prefix = None
                if src_col_lower.endswith("_id"):
                    prefix = src_col_lower[:-3]
                elif src_col_lower.endswith("id") and len(src_col_lower) > 2:
                    prefix = src_col_lower[:-2]
                
                # Rule 1: Table ID match via prefix (Singular Table ID Pattern)
                if prefix and prefix in singular_to_table:
                    expected_tgt_table = singular_to_table[prefix]
                    if expected_tgt_table == tgt_table.name:
                        # Find an ID column in target table
                        for tgt_col in tgt_table.columns:
                            if tgt_col.name.lower() == "id":
                                if not is_seen_or_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
                                    relationships.append(RelationshipSchema(
                                        source_table=src_table.name,
                                        source_column=src_col.name,
                                        target_table=tgt_table.name,
                                        target_column=tgt_col.name,
                                        relationship_type=RelationshipType.IMPLICIT,
                                        confidence=0.90,
                                        reason="singular_table_id_pattern",
                                        raw={"rule": "singular_table_id_pattern", "matched_prefix": prefix}
                                    ))
                                break # Move to next source column
                
                # Rule 2: Prefix-to-Table_Name Fuzzy Match
                elif prefix:
                    # Generic prefix check (e.g. if the prefix is 'status', we shouldn't match it fuzzily to 'statuses')
                    # We just use difflib to compare prefix with target singular name
                    tgt_singular = get_singular(tgt_table.name)
                    if probe is not None:
                        probe.incr("fuzzy_comparison")
                    ratio = difflib.SequenceMatcher(None, prefix, tgt_singular).ratio()
                    
                    if ratio >= 0.85:
                        confidence = 0.75 if ratio >= 0.90 else 0.65
                        for tgt_col in tgt_table.columns:
                            if tgt_col.name.lower() == "id":
                                if not is_seen_or_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
                                    relationships.append(RelationshipSchema(
                                        source_table=src_table.name,
                                        source_column=src_col.name,
                                        target_table=tgt_table.name,
                                        target_column=tgt_col.name,
                                        relationship_type=RelationshipType.IMPLICIT_FUZZY,
                                        confidence=confidence,
                                        reason="fuzzy_prefix_to_table_match",
                                        raw={"rule": "fuzzy_prefix_match", "ratio": ratio, "prefix": prefix}
                                    ))
                                break

                # Rule 3: Exact column name match (only if not generic)
                if not is_generic_column(src_col_lower):
                    if probe is not None:
                        probe.incr("rule3_scan")
                    for tgt_col in tgt_table.columns:
                        tgt_col_lower = tgt_col.name.lower()
                        if src_col_lower == tgt_col_lower:
                            # Exact match on a non-generic column
                            if not is_seen_or_explicit(src_table.name, src_col.name, tgt_table.name, tgt_col.name):
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
                            break

    return relationships
