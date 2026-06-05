from typing import Any
from .schema_contract import (
    DatabaseSchema,
    TableSchema,
    ColumnSchema,
    RelationshipSchema,
    SchemaGraph,
    RelationshipType
)

def from_legacy_schema(raw_schema: dict[str, Any], dialect: str | None = None) -> DatabaseSchema:
    """
    Parses a legacy dictionary schema into a strongly-typed DatabaseSchema.
    
    This function prioritizes `graph.edges` as the source of truth for relationships.
    If `graph.edges` is absent or explicitly empty, it falls back to parsing
    `foreign_keys` arrays from individual tables.
    """
    if dialect is None:
        dialect = "unknown"
        
    if not isinstance(raw_schema, dict):
        raise ValueError("Legacy schema must be a dictionary")
        
    if "tables" not in raw_schema or not isinstance(raw_schema["tables"], dict):
        raise ValueError("Legacy schema must contain a 'tables' object (dict)")

    tables = []
    relationships = []
    
    raw_tables = raw_schema["tables"]
    for table_name, table_data in raw_tables.items():
        if not isinstance(table_data, dict):
            raise ValueError(f"Table '{table_name}' metadata must be a dictionary")
            
        columns = []
        pk_cols = []
        
        raw_columns = table_data.get("columns", [])
        if not isinstance(raw_columns, list):
            raise ValueError(f"Table '{table_name}' columns must be a list")
            
        for i, col_data in enumerate(raw_columns):
            if not isinstance(col_data, dict):
                raise ValueError(f"Table '{table_name}' column[{i}] must be a dictionary")
                
            col = ColumnSchema(
                name=col_data.get("name", ""),
                data_type=col_data.get("type"),
                primary_key=col_data.get("primary_key", False),
                nullable=col_data.get("nullable"),
                raw=col_data
            )
            columns.append(col)
            if col.primary_key:
                pk_cols.append(col.name)
                
        tables.append(TableSchema(
            name=table_name,
            columns=columns,
            primary_key_columns=pk_cols,
            raw=table_data
        ))
        
    raw_graph = raw_schema.get("graph")
    if raw_graph is not None and not isinstance(raw_graph, dict):
        raise ValueError("Legacy schema 'graph' must be a dictionary if present")

    has_graph_edges = False
    nodes = []
    if raw_graph and isinstance(raw_graph, dict):
        nodes = raw_graph.get("nodes", [])
        if not isinstance(nodes, list):
            raise ValueError("Legacy schema 'graph.nodes' must be a list if present")
            
        raw_edges = raw_graph.get("edges")
        if raw_edges is not None:
            if not isinstance(raw_edges, list):
                raise ValueError("Legacy schema 'graph.edges' must be a list if present")
            
            # Using bool(raw_edges) ensures fallback triggers if edges is an empty list []
            if raw_edges:
                has_graph_edges = True
                
            for i, edge in enumerate(raw_edges):
                if not isinstance(edge, dict):
                    raise ValueError(f"Graph edge[{i}] must be a dictionary")
                    
                rel_type_str = edge.get("type", "explicit")
                try:
                    rel_type = RelationshipType(rel_type_str)
                except ValueError as exc:
                    raise ValueError(f"Unknown relationship type in graph edge[{i}]: {rel_type_str}") from exc
                    
                rel = RelationshipSchema(
                    source_table=edge.get("source", ""),
                    source_column=edge.get("source_col", ""),
                    target_table=edge.get("target", ""),
                    target_column=edge.get("target_col", ""),
                    relationship_type=rel_type,
                    raw=edge
                )
                relationships.append(rel)
    
    if not has_graph_edges:
        for table_name, table_data in raw_tables.items():
            raw_fks = table_data.get("foreign_keys", [])
            if not isinstance(raw_fks, list):
                raise ValueError(f"Table '{table_name}' foreign_keys must be a list")
                
            for i, fk in enumerate(raw_fks):
                if not isinstance(fk, dict):
                    raise ValueError(f"Table '{table_name}' foreign_key[{i}] must be a dictionary")
                    
                rel_type_str = fk.get("type", "explicit")
                try:
                    rel_type = RelationshipType(rel_type_str)
                except ValueError as exc:
                    raise ValueError(f"Unknown relationship type in table '{table_name}' foreign_keys[{i}]: {rel_type_str}") from exc
                    
                rel = RelationshipSchema(
                    source_table=table_name,
                    source_column=fk.get("column", ""),
                    target_table=fk.get("referenced_table", ""),
                    target_column=fk.get("referenced_column", ""),
                    relationship_type=rel_type,
                    raw=fk
                )
                relationships.append(rel)

    # For graph, if we fell back to fks and nodes are empty, auto-generate nodes
    if not has_graph_edges and not nodes:
        nodes = list(raw_tables.keys())

    graph = SchemaGraph(nodes=nodes, edges=relationships)
    
    return DatabaseSchema(
        dialect=dialect,
        tables=tables,
        relationships=relationships,
        graph=graph,
        raw=raw_schema
    )

def to_legacy_dict(schema: DatabaseSchema) -> dict[str, Any]:
    """
    Serializes a DatabaseSchema back to the legacy dictionary format.
    
    Note: Graph edges are correctly serialized back into `graph.edges`. However, 
    table `foreign_keys` lists are restored *only* from the raw data if they existed.
    Implicit graph edges are NOT injected into table `foreign_keys` to prevent
    polluting the database-level constraint semantic boundary.
    """
    legacy = {
        "tables": {},
        "graph": {
            "nodes": [],
            "edges": []
        }
    }
    
    if schema.graph:
        legacy["graph"]["nodes"] = schema.graph.nodes
        for edge in schema.graph.edges:
            edge_dict = {
                "source": edge.source_table,
                "target": edge.target_table,
                "source_col": edge.source_column,
                "target_col": edge.target_column,
                "type": edge.relationship_type.value
            }
            for k, v in edge.raw.items():
                if k not in edge_dict:
                    edge_dict[k] = v
            legacy["graph"]["edges"].append(edge_dict)
            
    for table in schema.tables:
        t_dict = {
            "columns": [],
            "foreign_keys": [],
            "constraints": []
        }
        
        for k, v in table.raw.items():
            if k not in ["columns", "foreign_keys", "constraints"]:
                t_dict[k] = v
                
        for col in table.columns:
            c_dict = {
                "name": col.name,
                "type": col.data_type,
                "primary_key": col.primary_key,
                "nullable": col.nullable
            }
            for k, v in col.raw.items():
                if k not in c_dict:
                    c_dict[k] = v
            if c_dict.get("nullable") is None and "nullable" not in col.raw:
                c_dict.pop("nullable")
            t_dict["columns"].append(c_dict)
            
        # Only restore original table-level raw foreign keys. 
        # DO NOT automatically merge from graph.edges to prevent implicit/custom polluting DB constraint semantics
        if "foreign_keys" in table.raw:
            t_dict["foreign_keys"] = table.raw["foreign_keys"]
                
        if "constraints" in table.raw:
            t_dict["constraints"] = table.raw["constraints"]
            
        legacy["tables"][table.name] = t_dict
        
    for k, v in schema.raw.items():
        if k not in legacy:
            legacy[k] = v

    return legacy
