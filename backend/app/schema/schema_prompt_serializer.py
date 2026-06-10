from app.schema.schema_contract import DatabaseSchema, RelationshipType, TableSchema, ColumnSchema
from app.schema.graph_traversal import JoinPathCandidate

# Using the priority mapping from graph traversal or defining it locally
# Since we need it, let's redefine it or import it. It's safer to import or define locally.
RELATIONSHIP_TYPE_PRIORITY = {
    RelationshipType.EXPLICIT: 100,
    RelationshipType.CUSTOM: 90,
    RelationshipType.IMPLICIT: 60,
    RelationshipType.IMPLICIT_FUZZY: 40,
}

def serialize_schema_for_prompt(
    schema: DatabaseSchema,
    *,
    focus_tables: list[str] | None = None,
    join_paths: list[JoinPathCandidate] | None = None,
    max_tables: int = 20,
    max_columns_per_table: int = 30,
    include_relationships: bool = True,
    include_confidence: bool = True,
) -> str:
    """
    Serializes the database schema into a deterministic, token-budgeted markdown format
    for LLM prompt context.
    """
    focus_tables = focus_tables or []
    join_paths = join_paths or []
    
    # Extract unique tables from join paths in order of appearance
    join_path_table_names = []
    for path in join_paths:
        for t in path.tables:
            if t not in join_path_table_names:
                join_path_table_names.append(t)
                
    # Function to get table sort key
    def table_sort_key(table: TableSchema) -> tuple:
        is_focus = 0 if table.name in focus_tables else 1
        focus_idx = focus_tables.index(table.name) if table.name in focus_tables else 0
        
        is_join = 0 if table.name in join_path_table_names else 1
        join_idx = join_path_table_names.index(table.name) if table.name in join_path_table_names else 0
        
        return (is_focus, focus_idx, is_join, join_idx, table.name)

    # Sort and slice tables
    sorted_tables = sorted(schema.tables, key=table_sort_key)
    selected_tables = sorted_tables[:max_tables]
    selected_table_names = {t.name for t in selected_tables}
    
    lines = ["Schema Context\n", "Tables:"]
    
    for table in selected_tables:
        lines.append(table.name)
        
        # Sort and slice columns
        # Primary keys first, then original order (which is their index in table.columns)
        def column_sort_key(item: tuple[int, ColumnSchema]) -> tuple:
            idx, col = item
            is_pk = 0 if col.primary_key else 1
            return (is_pk, idx)
            
        enumerated_cols = list(enumerate(table.columns))
        sorted_cols = sorted(enumerated_cols, key=column_sort_key)
        selected_cols = [col for _, col in sorted_cols[:max_columns_per_table]]
        
        for col in selected_cols:
            col_type = col.data_type if col.data_type else "UNKNOWN"
            pk_str = " primary_key" if col.primary_key else ""
            lines.append(f"  - {col.name} {col_type}{pk_str}")
            
        lines.append("") # Empty line after table
        
    if include_relationships and schema.relationships:
        lines.append("Relationships:")
        
        # Filter relationships to only include those between selected tables
        valid_rels = [
            r for r in schema.relationships 
            if r.source_table in selected_table_names and r.target_table in selected_table_names
            and r.relationship_type != RelationshipType.DISABLED
        ]
        
        def rel_sort_key(rel) -> tuple:
            priority = RELATIONSHIP_TYPE_PRIORITY.get(rel.relationship_type, 0)
            return (
                -priority,
                rel.source_table,
                rel.source_column,
                rel.target_table,
                rel.target_column
            )
            
        sorted_rels = sorted(valid_rels, key=rel_sort_key)
        
        for rel in sorted_rels:
            type_str = rel.relationship_type.value
            details = [type_str]
            
            if include_confidence and rel.relationship_type in (RelationshipType.IMPLICIT, RelationshipType.IMPLICIT_FUZZY):
                if rel.confidence is not None:
                    # Format float to 2 decimal places exactly
                    details.append(f"confidence={rel.confidence:.2f}")
                if rel.reason:
                    details.append(f"reason={rel.reason}")
                    
            details_str = " ".join(details)
            lines.append(f"  - [{details_str}] {rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}")
            
        lines.append("") # Empty line
        
    if join_paths:
        lines.append("Join Paths:")
        for path in join_paths:
            path_str = " -> ".join(path.tables)
            lines.append(f"  {path_str}")
            
            for edge in path.edges:
                type_str = edge.relationship_type.value
                details = [type_str]
                
                if include_confidence and edge.relationship_type in (RelationshipType.IMPLICIT, RelationshipType.IMPLICIT_FUZZY):
                    if edge.confidence is not None:
                        details.append(f"confidence={edge.confidence:.2f}")
                    if edge.reason:
                        details.append(f"reason={edge.reason}")
                        
                details_str = " ".join(details)
                lines.append(f"    - [{details_str}] {edge.relationship_source_table}.{edge.relationship_source_column} -> {edge.relationship_target_table}.{edge.relationship_target_column}")
                
        lines.append("")
        
    return "\n".join(lines).strip()
