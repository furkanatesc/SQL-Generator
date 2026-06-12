from dataclasses import dataclass
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema

SCHEMA_SUMMARY_VERSION = "schema_summary_v1"


def format_type(data_type: str | None) -> str:
    """
    Standardizes and formats data types to uppercase (e.g. VARCHAR).
    Maps INT to INTEGER for SQLite compatibility.
    """
    if not data_type:
        return "none"
    u = data_type.upper()
    if u == "INT":
        return "INTEGER"
    return u


@dataclass(frozen=True)
class ColumnSummary:
    table_name: str
    column_name: str
    data_type: str | None
    nullable: bool | None
    primary_key: bool = False
    semantic_tags: tuple[str, ...] = ()

    @property
    def summary_version(self) -> str:
        return SCHEMA_SUMMARY_VERSION

    @property
    def summary_text(self) -> str:
        type_str = format_type(self.data_type)
        nullable_str = str(self.nullable).lower() if self.nullable is not None else "none"
        tags_str = ",".join(self.semantic_tags)
        return (
            f"COLUMN {self.table_name}.{self.column_name}\n"
            f"TYPE: {type_str}\n"
            f"NULLABLE: {nullable_str}\n"
            f"TAGS: {tags_str}\n"
            f"VERSION: {self.summary_version}"
        )



@dataclass(frozen=True)
class RelationshipSummary:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str
    confidence: float | None = None

    @property
    def summary_version(self) -> str:
        return SCHEMA_SUMMARY_VERSION

    @property
    def summary_text(self) -> str:
        confidence_str = str(self.confidence) if self.confidence is not None else "none"
        return (
            f"RELATIONSHIP {self.source_table}.{self.source_column} -> {self.target_table}.{self.target_column}\n"
            f"TYPE: {self.relationship_type}\n"
            f"CONFIDENCE: {confidence_str}\n"
            f"VERSION: {self.summary_version}"
        )


@dataclass(frozen=True)
class TableSummary:
    table_name: str
    columns: tuple[ColumnSummary, ...]
    relationships: tuple[RelationshipSummary, ...]
    summary_text: str
    summary_version: str


def generate_table_summary_text(
    table_name: str,
    columns: list[ColumnSummary],
    relationships: list[RelationshipSummary]
) -> str:
    """
    Generates a deterministic multiline string summary for a table.
    Columns are sorted by column_name.
    Relationships are sorted by source_table, source_column, target_table, target_column.
    """
    lines = [f"TABLE {table_name}"]
    lines.append("COLUMNS:")
    
    # Ensure columns are sorted by column_name
    sorted_cols = sorted(columns, key=lambda c: c.column_name)
    for col in sorted_cols:
        col_line = f"- {col.column_name}"
        if col.data_type:
            col_line += f" {format_type(col.data_type)}"
        if col.primary_key:
            col_line += " pk"
        lines.append(col_line)
        
    lines.append("RELATIONSHIPS:")
    
    # Ensure relationships are sorted by source_table, source_column, target_table, target_column
    sorted_rels = sorted(
        relationships,
        key=lambda r: (r.source_table, r.source_column, r.target_table, r.target_column)
    )
    for rel in sorted_rels:
        lines.append(
            f"- {rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column} {rel.relationship_type}"
        )
        
    lines.append(f"VERSION: {SCHEMA_SUMMARY_VERSION}")
    return "\n".join(lines)


def summarize_column(table: TableSchema, column: ColumnSchema) -> ColumnSummary:
    """
    Summarizes a column from a TableSchema and ColumnSchema.
    Tags are extracted from raw metadata (checked key 'semantic_tags' then fallback 'tags')
    and sorted alphabetically.
    """
    raw_tags = []
    if column.raw:
        raw_tags = column.raw.get("semantic_tags", [])
        if not raw_tags:
            raw_tags = column.raw.get("tags", [])

    # Ensure tags is a flat list of strings
    if isinstance(raw_tags, str):
        tags_list = [raw_tags]
    elif isinstance(raw_tags, (list, tuple)):
        tags_list = [str(t) for t in raw_tags]
    else:
        tags_list = []

    sorted_tags = tuple(sorted(tags_list))

    return ColumnSummary(
        table_name=table.name,
        column_name=column.name,
        data_type=column.data_type,
        nullable=column.nullable,
        primary_key=column.primary_key,
        semantic_tags=sorted_tags
    )


def summarize_relationship(rel: RelationshipSchema) -> RelationshipSummary:
    """
    Summarizes a relationship from a RelationshipSchema.
    """
    rel_type_str = rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type)
    return RelationshipSummary(
        source_table=rel.source_table,
        source_column=rel.source_column,
        target_table=rel.target_table,
        target_column=rel.target_column,
        relationship_type=rel_type_str,
        confidence=rel.confidence
    )


def summarize_table(schema: DatabaseSchema, table_name: str) -> TableSummary:
    """
    Summarizes a specific table within a DatabaseSchema.
    Includes columns inside the table and all relationships associated with the table
    (either as source_table or target_table), preserving original direction.
    """
    table = next((t for t in schema.tables if t.name == table_name), None)
    if not table:
        raise ValueError(f"Table '{table_name}' not found in database schema.")

    column_summaries = []
    for col in table.columns:
        column_summaries.append(summarize_column(table, col))

    # Collect unique relationships involving this table (source_table or target_table)
    all_rels = schema.relationships or []
    if schema.graph and schema.graph.edges:
        if not all_rels:
            all_rels = schema.graph.edges

    rel_summaries = []
    seen_rels = set()
    for rel in all_rels:
        if rel.source_table == table_name or rel.target_table == table_name:
            rel_key = (rel.source_table, rel.source_column, rel.target_table, rel.target_column)
            if rel_key not in seen_rels:
                seen_rels.add(rel_key)
                rel_summaries.append(summarize_relationship(rel))

    column_tuple = tuple(sorted(column_summaries, key=lambda c: c.column_name))
    rel_tuple = tuple(sorted(
        rel_summaries,
        key=lambda r: (r.source_table, r.source_column, r.target_table, r.target_column)
    ))

    summary_text = generate_table_summary_text(table_name, list(column_tuple), list(rel_tuple))

    return TableSummary(
        table_name=table_name,
        columns=column_tuple,
        relationships=rel_tuple,
        summary_text=summary_text,
        summary_version=SCHEMA_SUMMARY_VERSION
    )


def summarize_database_schema(schema: DatabaseSchema) -> list[TableSummary]:
    """
    Summarizes all tables in a DatabaseSchema.
    Returns the summaries sorted by table_name.
    """
    table_summaries = []
    sorted_tables = sorted(schema.tables, key=lambda t: t.name)
    for table in sorted_tables:
        table_summaries.append(summarize_table(schema, table.name))
    return table_summaries
