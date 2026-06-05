from .schema_contract import (
    DatabaseSchema,
    TableSchema,
    ColumnSchema,
    RelationshipSchema,
    SchemaGraph,
    RelationshipType
)
from .schema_adapter import from_legacy_schema, to_legacy_dict

__all__ = [
    "DatabaseSchema",
    "TableSchema",
    "ColumnSchema",
    "RelationshipSchema",
    "SchemaGraph",
    "RelationshipType",
    "from_legacy_schema",
    "to_legacy_dict"
]
