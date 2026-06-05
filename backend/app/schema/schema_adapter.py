from typing import Dict, Any
from .schema_contract import (
    DatabaseSchema,
    TableSchema,
    ColumnSchema,
    RelationshipSchema,
    SchemaGraph,
    RelationshipType
)

def from_legacy_schema(raw_schema: Dict[str, Any], dialect: str | None = None) -> DatabaseSchema:
    if dialect is None:
        dialect = "unknown"
        
    tables = []
    relationships = []
    
    # Parse tables
    raw_tables = raw_schema.get("tables", {})
    for table_name, table_data in raw_tables.items():
        columns = []
        pk_cols = []
        
        for col_data in table_data.get("columns", []):
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
        
    # Parse graph edges
    raw_graph = raw_schema.get("graph", {})
    nodes = raw_graph.get("nodes", [])
    raw_edges = raw_graph.get("edges", [])
    
    for edge in raw_edges:
        rel_type_str = edge.get("type", "explicit")
        try:
            rel_type = RelationshipType(rel_type_str)
        except ValueError:
            rel_type = RelationshipType.CUSTOM
            
        rel = RelationshipSchema(
            source_table=edge.get("source", ""),
            source_column=edge.get("source_col", ""),
            target_table=edge.get("target", ""),
            target_column=edge.get("target_col", ""),
            relationship_type=rel_type,
            raw=edge
        )
        relationships.append(rel)
        
    graph = SchemaGraph(nodes=nodes, edges=relationships)
    
    return DatabaseSchema(
        dialect=dialect,
        tables=tables,
        relationships=relationships,
        graph=graph,
        raw=raw_schema
    )

def to_legacy_dict(schema: DatabaseSchema) -> Dict[str, Any]:
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
            # restore other keys from raw if they exist
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
        
        # restore table raw fields
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
            # remove None values for nullable if they weren't there originally to avoid bloating
            if c_dict.get("nullable") is None and "nullable" not in col.raw:
                c_dict.pop("nullable")
            t_dict["columns"].append(c_dict)
            
        # Restore foreign_keys array from original raw format,
        # but also ensure all edges stemming from this table are included
        # to handle cases where relationships were added functionally.
        existing_fks = set()
        if "foreign_keys" in table.raw:
            for raw_fk in table.raw["foreign_keys"]:
                t_dict["foreign_keys"].append(raw_fk)
                existing_fks.add((raw_fk.get("column"), raw_fk.get("referenced_table")))
                
        for edge in legacy["graph"]["edges"]:
            if edge["source"] == table.name:
                if (edge["source_col"], edge["target"]) not in existing_fks:
                    fk_dict = {
                        "column": edge["source_col"],
                        "referenced_table": edge["target"],
                        "referenced_column": edge["target_col"],
                        "type": edge["type"]
                    }
                    t_dict["foreign_keys"].append(fk_dict)
                
        if "constraints" in table.raw:
            t_dict["constraints"] = table.raw["constraints"]
            
        legacy["tables"][table.name] = t_dict
        
    # Also restore any top-level raw fields like sequences or embeddings
    for k, v in schema.raw.items():
        if k not in legacy:
            legacy[k] = v

    return legacy
