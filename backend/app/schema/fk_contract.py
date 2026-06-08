from typing import Any
from .schema_contract import RelationshipSchema, RelationshipType

def explicit_fk_relationship(
    *,
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    raw: dict[str, Any] | None = None
) -> RelationshipSchema:
    """
    Creates a standard explicit foreign key relationship.
    
    Contract rules:
    - source_table.source_column MUST represent the table and column holding the foreign key (child).
    - target_table.target_column MUST represent the referenced table and column (parent).
    """
    if raw is None:
        raw = {}
        
    return RelationshipSchema(
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column=target_column,
        relationship_type=RelationshipType.EXPLICIT,
        raw=raw
    )
