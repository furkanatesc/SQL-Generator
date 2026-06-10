from app.schema.schema_contract import DatabaseSchema, RelationshipType
from app.schema.schema_context_selector import SchemaContextSelection

def serialize_schema_for_prompt(schema: DatabaseSchema, selection: SchemaContextSelection) -> str:
    """
    Serializes a subset of the DatabaseSchema to a text format for the LLM prompt,
    bounded by the selected tables and relationships/join paths from the Context Selector.
    """
    selected_table_names = {st.table_name for st in selection.selected_tables}
    
    for path in selection.join_paths:
        selected_table_names.update(path.tables)
    
    schema_text = ""
    
    # 1. Tables and Columns
    for table in schema.tables:
        if table.name in selected_table_names:
            schema_text += f"TABLE {table.name}\n"
            schema_text += "  Columns:\n"
            for col in table.columns:
                pk_str = " (PRIMARY KEY)" if col.primary_key else ""
                nullable_str = "" if col.nullable else " NOT NULL"
                type_str = f": {col.data_type}" if col.data_type else ""
                schema_text += f"    - {col.name}{type_str}{pk_str}{nullable_str}\n"
            schema_text += "\n"
            
    # 2. Induced Relationships from Selected Tables
    induced_relationships = []
    excluded_types = {RelationshipType.DISABLED, RelationshipType.IMPLICIT_FUZZY}
    
    for rel in schema.relationships:
        if rel.source_table in selected_table_names and rel.target_table in selected_table_names:
            if rel.relationship_type not in excluded_types:
                induced_relationships.append(rel)
            
    if induced_relationships:
        schema_text += "RELATIONSHIPS:\n"
        for rel in induced_relationships:
            type_str = ""
            if rel.relationship_type == RelationshipType.IMPLICIT:
                type_str = f" [implicit{f', confidence: {rel.confidence}' if rel.confidence else ''}]"
            elif rel.relationship_type == RelationshipType.CUSTOM:
                type_str = " [virtual/custom]"
            elif rel.relationship_type == RelationshipType.EXPLICIT:
                type_str = " [explicit]"
            
            schema_text += f"  - {rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}{type_str}\n"
        schema_text += "\n"
        
    # 3. Join Paths
    if selection.join_paths:
        schema_text += "JOIN PATHS:\n"
        for path in selection.join_paths:
            path_str = " -> ".join(path.tables)
            schema_text += f"  - JOIN PATH: {path_str}\n"
            for edge in path.edges:
                rel_type = edge.relationship_type.value if edge.relationship_type else "explicit"
                schema_text += f"    - {edge.relationship_source_table}.{edge.relationship_source_column} -> {edge.relationship_target_table}.{edge.relationship_target_column} [{rel_type}]\n"
        schema_text += "\n"
        
    return schema_text.strip()
