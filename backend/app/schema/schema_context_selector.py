import re
from pydantic import BaseModel
from app.schema.schema_contract import DatabaseSchema, RelationshipType, TableSchema
from app.schema.graph_traversal import JoinPathCandidate, find_join_paths

class SelectedTable(BaseModel):
    table_name: str
    score: float
    reasons: list[str]

class SchemaContextSelection(BaseModel):
    focus_tables: list[str]
    selected_tables: list[SelectedTable]
    join_paths: list[JoinPathCandidate]

def _tokenize(text: str) -> set[str]:
    """Simple tokenizer that splits by non-alphanumeric characters and lowercases."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))

def _singularize(word: str) -> str:
    """Very basic plural to singular mapping for matching."""
    if word.endswith('ies'):
        return word[:-3] + 'y'
    if word.endswith('es') and not word.endswith('sses'):
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word

def select_schema_context(
    schema: DatabaseSchema,
    question: str,
    *,
    max_tables: int = 8,
    max_join_paths: int = 5,
    include_related_tables: bool = True,
) -> SchemaContextSelection:
    """
    Deterministically selects and scores relevant tables from the database schema based on the question.
    """
    question_tokens = _tokenize(question)
    question_singular_tokens = {_singularize(t) for t in question_tokens}
    
    table_scores: dict[str, float] = {}
    table_reasons: dict[str, list[str]] = {}
    
    def add_score(table_name: str, score: float, reason: str):
        if table_name not in table_scores:
            table_scores[table_name] = 0.0
            table_reasons[table_name] = []
        table_scores[table_name] += score
        table_reasons[table_name].append(reason)
        
    for table in schema.tables:
        table_tokens = _tokenize(table.name)
        table_singular_tokens = {_singularize(t) for t in table_tokens}
        
        # Table Exact Match
        if table.name.lower() in question.lower():
            add_score(table.name, 100.0, "exact_table_match")
            
        # Table Singular/Plural Match
        elif table_singular_tokens & question_singular_tokens:
            add_score(table.name, 60.0, "singular_plural_table_match")
            
        # Table Token Overlap
        elif table_tokens & question_tokens:
            add_score(table.name, 40.0, "table_token_overlap")
            
        # Column Matches
        has_exact_col = False
        has_overlap_col = False
        for col in table.columns:
            if col.name.lower() in question.lower():
                has_exact_col = True
            else:
                col_tokens = _tokenize(col.name)
                if col_tokens & question_tokens:
                    has_overlap_col = True
                    
        if has_exact_col:
            add_score(table.name, 80.0, "exact_column_match")
        elif has_overlap_col:
            add_score(table.name, 30.0, "column_token_overlap")
            
    # Apply Relationship-aware Expansion
    if include_related_tables:
        base_selected = [t for t in table_scores.keys() if table_scores[t] > 0]
        for t_name in base_selected:
            for rel in schema.relationships:
                if rel.source_table == t_name or rel.target_table == t_name:
                    neighbor = rel.target_table if rel.source_table == t_name else rel.source_table
                    
                    if rel.relationship_type in (RelationshipType.EXPLICIT, RelationshipType.CUSTOM):
                        add_score(neighbor, 20.0, f"explicit_neighbor_of_{t_name}")
                    elif rel.relationship_type == RelationshipType.IMPLICIT:
                        add_score(neighbor, 10.0, f"implicit_neighbor_of_{t_name}")
                    # implicit_fuzzy is not trusted to expand by default
                        
    # Sort and pick top K
    selected_tables = []
    for t_name, score in table_scores.items():
        if score > 0:
            selected_tables.append(SelectedTable(table_name=t_name, score=score, reasons=table_reasons[t_name]))
            
    selected_tables.sort(key=lambda st: (-st.score, st.table_name))
    selected_tables = selected_tables[:max_tables]
    
    focus_tables = [st.table_name for st in selected_tables]
    
    # Discover Join Paths among top tables
    join_paths = []
    top_tables = focus_tables[:5] # Limit combinations to top 5
    for i in range(len(top_tables)):
        for j in range(i + 1, len(top_tables)):
            source = top_tables[i]
            target = top_tables[j]
            paths = find_join_paths(
                schema,
                source,
                target,
                max_depth=3,
                max_paths=1,
                allow_fuzzy=False
            )
            join_paths.extend(paths)
            
    # Remove duplicates and limit
    unique_paths = []
    seen = set()
    for p in join_paths:
        key = str(p.tables)
        if key not in seen:
            seen.add(key)
            unique_paths.append(p)
            
    unique_paths = unique_paths[:max_join_paths]

    return SchemaContextSelection(
        focus_tables=focus_tables,
        selected_tables=selected_tables,
        join_paths=unique_paths
    )
