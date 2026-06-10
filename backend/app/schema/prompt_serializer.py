from app.schema.schema_contract import DatabaseSchema
from app.schema.schema_context_selector import SchemaContextSelection

def serialize_schema_for_prompt(schema: DatabaseSchema, selection: SchemaContextSelection) -> str:
    """
    Serializes a subset of the DatabaseSchema to a text format for the LLM prompt,
    bounded by the selected tables and relationships/join paths from the Context Selector.
    """
    selected_table_names = {st.table_name for st in selection.selected_tables}
    
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
    for rel in schema.relationships:
        if rel.source_table in selected_table_names and rel.target_table in selected_table_names:
            induced_relationships.append(rel)
            
    if induced_relationships:
        schema_text += "RELATIONSHIPS:\n"
        for rel in induced_relationships:
            rel_type = rel.relationship_type.value
            type_str = ""
            if rel_type == "implicit":
                type_str = " (Implicit Relation)"
            elif rel_type == "custom":
                type_str = " (Virtual/Custom Relation)"
            
            schema_text += f"  - {rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}{type_str}\n"
        schema_text += "\n"
        
    # 3. Join Paths
    if selection.join_paths:
        schema_text += "JOIN PATHS:\n"
        for path in selection.join_paths:
            path_str = " -> ".join(path.tables)
            schema_text += f"  - JOIN PATH: {path_str}\n"
        schema_text += "\n"
        
    return schema_text.strip()
