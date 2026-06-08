from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class RelationshipType(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"
    CUSTOM = "custom"
    DISABLED = "disabled"
    IMPLICIT_FUZZY = "implicit_fuzzy"


class ColumnSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    data_type: str | None = None
    nullable: bool | None = None
    primary_key: bool = False
    unique: bool = False
    default: str | None = None
    ordinal_position: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_name(self) -> "ColumnSchema":
        if not self.name.strip():
            raise ValueError("Column name cannot be empty")
        return self


class TableSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    schema_name: str | None = None
    columns: list[ColumnSchema]
    primary_key_columns: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_table(self) -> "TableSchema":
        if not self.name.strip():
            raise ValueError("Table name cannot be empty")
        if not self.columns:
            raise ValueError("Table must have at least one column")
        
        col_names = [c.name.lower() for c in self.columns]
        if len(col_names) != len(set(col_names)):
            raise ValueError(f"Duplicate column names detected in table '{self.name}' (case-insensitive check)")
            
        return self


class RelationshipSchema(BaseModel):
    """
    Contract for a relationship between two tables.
    
    DIRECTION CONTRACT FOR FOREIGN KEYS:
    - source_table / source_column: MUST be the table and column that contains the foreign key (child table).
    - target_table / target_column: MUST be the referenced table and column (parent table).
    This direction is strictly enforced and must never be reversed.
    """
    model_config = ConfigDict(extra="forbid")

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: RelationshipType = RelationshipType.EXPLICIT
    confidence: float | None = None
    reason: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_relationship(self) -> "RelationshipSchema":
        if not self.source_table.strip() or not self.target_table.strip():
            raise ValueError("Source and target table names cannot be empty")
        if not self.source_column.strip() or not self.target_column.strip():
            raise ValueError("Source and target column names cannot be empty")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return self


class SchemaGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[str]
    edges: list[RelationshipSchema]

    @model_validator(mode="after")
    def validate_graph(self) -> "SchemaGraph":
        for i, node in enumerate(self.nodes):
            if not node.strip():
                raise ValueError(f"Graph nodes cannot be empty strings (at index {i})")
        if len(self.nodes) != len(set(self.nodes)):
            raise ValueError("Graph contains duplicate nodes")
            
        node_set = set(self.nodes)
        for i, edge in enumerate(self.edges):
            if edge.source_table not in node_set:
                raise ValueError(f"Graph edge[{i}] source_table references unknown node: '{edge.source_table}'")
            if edge.target_table not in node_set:
                raise ValueError(f"Graph edge[{i}] target_table references unknown node: '{edge.target_table}'")
        return self


class DatabaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialect: str
    database_name: str | None = None
    tables: list[TableSchema]
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    graph: SchemaGraph | None = None
    version: str = "schema-contract-v1"
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_database_schema(self) -> "DatabaseSchema":
        table_names = [t.name for t in self.tables]
        if len(table_names) != len(set(table_names)):
            raise ValueError("Duplicate table names detected in database schema")

        table_dict = {t.name: t for t in self.tables}

        if self.graph:
            node_set = set(self.graph.nodes)
            table_set = set(table_names)
            if node_set != table_set:
                missing_in_graph = table_set - node_set
                missing_in_tables = node_set - table_set
                raise ValueError(
                    f"Graph nodes and table names do not match. "
                    f"Missing in graph: {missing_in_graph}. "
                    f"Missing in tables: {missing_in_tables}."
                )

            # Enforce semantic equality between relationships and graph.edges
            if self.relationships:
                rel_set = set((r.source_table, r.source_column, r.target_table, r.target_column, r.relationship_type) for r in self.relationships)
                graph_edge_set = set((r.source_table, r.source_column, r.target_table, r.target_column, r.relationship_type) for r in self.graph.edges)
                
                if rel_set != graph_edge_set:
                    raise ValueError(
                        "DatabaseSchema relationships and SchemaGraph edges must represent the exact same semantic edge set."
                    )

        all_edges = []
        if self.graph:
            all_edges.extend(self.graph.edges)
        if self.relationships:
            all_edges.extend(self.relationships)

        for i, edge in enumerate(all_edges):
            if edge.source_table not in table_dict:
                raise ValueError(f"Relationship source_table references unknown table: '{edge.source_table}'")
            
            if edge.target_table not in table_dict:
                raise ValueError(f"Relationship target_table references unknown table: '{edge.target_table}'")
            
            src_cols = [c.name.lower() for c in table_dict[edge.source_table].columns]
            if edge.source_column.lower() not in src_cols:
                raise ValueError(
                    f"Relationship source_column '{edge.source_column}' not found in table '{edge.source_table}'"
                )
                
            tgt_cols = [c.name.lower() for c in table_dict[edge.target_table].columns]
            if edge.target_column.lower() not in tgt_cols:
                raise ValueError(
                    f"Relationship target_column '{edge.target_column}' not found in table '{edge.target_table}'"
                )

        return self
