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
    def validate_name(self):
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
    def validate_table(self):
        if not self.name.strip():
            raise ValueError("Table name cannot be empty")
        if not self.columns:
            raise ValueError("Table must have at least one column")
        
        col_names = [c.name for c in self.columns]
        if len(col_names) != len(set(col_names)):
            raise ValueError("Duplicate column names are not allowed")
            
        return self


class RelationshipSchema(BaseModel):
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
    def validate_relationship(self):
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


class DatabaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialect: str
    database_name: str | None = None
    tables: list[TableSchema]
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    graph: SchemaGraph | None = None
    version: str = "schema-contract-v1"
    raw: dict[str, Any] = Field(default_factory=dict)
