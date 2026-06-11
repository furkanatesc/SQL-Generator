from app.schema.schema_contract import DatabaseSchema, RelationshipType, TableSchema, ColumnSchema
from app.schema.graph_traversal import JoinPathCandidate
from app.schema.relationship_priority import RELATIONSHIP_TYPE_PRIORITY
from app.schema.schema_context_selector import SchemaContextSelection

def serialize_selection_for_prompt(schema: DatabaseSchema, selection: SchemaContextSelection, max_columns_per_table: int = 15) -> str:
    allowed = set(selection.focus_tables)
    for p in selection.join_paths:
        allowed.update(p.tables)
        
    filtered_graph = None
    if schema.graph:
        from app.schema.schema_contract import SchemaGraph
        filtered_graph = SchemaGraph(
            nodes=list(allowed),
            edges=[e for e in schema.graph.edges if e.source_table in allowed and e.target_table in allowed]
        )
        
    filtered_schema = DatabaseSchema(
        dialect=schema.dialect,
        tables=[t for t in schema.tables if t.name in allowed],
        relationships=[r for r in schema.relationships if r.source_table in allowed and r.target_table in allowed],
        graph=filtered_graph,
        version=schema.version
    )
    
    return serialize_schema_for_prompt(
        schema=filtered_schema,
        focus_tables=selection.focus_tables,
        join_paths=selection.join_paths,
        max_tables=len(allowed),
        max_columns_per_table=max_columns_per_table
    )

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
    
    Caller Note: `join_paths` are serialized in the exact order they are provided. 
    It is the caller's responsibility to pass a deterministic list.
    """
    focus_tables = focus_tables or []
    join_paths = join_paths or []
    
    # Extract required columns and unique tables from relationships and join paths
    required_columns_by_table: dict[str, set[str]] = {}
    
    def mark_required(table_name: str, col_name: str):
        if table_name not in required_columns_by_table:
            required_columns_by_table[table_name] = set()
        required_columns_by_table[table_name].add(col_name)
        
    for rel in schema.relationships:
        if rel.relationship_type != RelationshipType.DISABLED:
            mark_required(rel.source_table, rel.source_column)
            mark_required(rel.target_table, rel.target_column)
            
    join_path_table_names = []
    for path in join_paths:
        for t in path.tables:
            if t not in join_path_table_names:
                join_path_table_names.append(t)
        for edge in path.edges:
            mark_required(edge.relationship_source_table, edge.relationship_source_column)
            mark_required(edge.relationship_target_table, edge.relationship_target_column)
                
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
        
        # Sort columns: PK first, then required relation cols, then original order
        def column_sort_key(item: tuple[int, ColumnSchema]) -> tuple:
            idx, col = item
            is_pk = 0 if col.primary_key else 1
            
            req_cols = required_columns_by_table.get(table.name, set())
            is_req = 0 if col.name in req_cols else 1
            
            return (is_pk, is_req, idx)
            
        enumerated_cols = list(enumerate(table.columns))
        sorted_cols = sorted(enumerated_cols, key=column_sort_key)
        
        # Select columns: enforce max_columns_per_table, but ALWAYS include required columns
        req_cols = required_columns_by_table.get(table.name, set())
        selected_cols = []
        for i, (_, col) in enumerate(sorted_cols):
            if i < max_columns_per_table or col.name in req_cols:
                selected_cols.append(col)
        
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
            and r.relationship_type not in (RelationshipType.DISABLED, RelationshipType.IMPLICIT_FUZZY)
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
