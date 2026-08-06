import re
from pydantic import BaseModel
from app.schema.schema_contract import DatabaseSchema, RelationshipType, TableSchema
from app.schema.graph_traversal import JoinPathCandidate, find_join_paths, DEFAULT_JOIN_PATH_NODE_BUDGET
from app.schema.table_selection_cost import (
    TableSelectionCostModel, DEFAULT_COST_MODEL, table_cost, fk_counts,
)

class SelectedTable(BaseModel):
    table_name: str
    score: float
    reasons: list[str]
    cost: float = 0.0

class SchemaContextSelection(BaseModel):
    focus_tables: list[str]
    selected_tables: list[SelectedTable]
    join_paths: list[JoinPathCandidate]
    fallback_used: bool = False
    fallback_strategy: str | None = None
    fallback_limit: int | None = None
    max_fallback_tables: int | None = None
    join_search_truncated: bool = False
    total_cost: float = 0.0
    cost_budget: float | None = None
    budget_exhausted: bool = False

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
    node_budget: int = DEFAULT_JOIN_PATH_NODE_BUDGET,
    cost_model: TableSelectionCostModel = DEFAULT_COST_MODEL,
    probe=None,
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
        if probe is not None:
            probe.incr("table_scan")
        table_tokens = _tokenize(table.name)
        table_singular_tokens = {_singularize(t) for t in table_tokens}
        
        # Table Exact Match
        if table.name.lower() in question.lower():
            add_score(table.name, cost_model.exact_table, "exact_table_match")

        # Table Singular/Plural Match
        elif table_singular_tokens & question_singular_tokens:
            add_score(table.name, cost_model.singular_plural_table, "singular_plural_table_match")

        # Table Token Overlap
        elif table_tokens & question_tokens:
            add_score(table.name, cost_model.table_token_overlap, "table_token_overlap")
            
        # Column Matches
        has_exact_col = False
        has_overlap_col = False
        for col in table.columns:
            if probe is not None:
                probe.incr("column_scan")
            if col.name.lower() in question.lower():
                has_exact_col = True
            else:
                col_tokens = _tokenize(col.name)
                if col_tokens & question_tokens:
                    has_overlap_col = True
                    
        if has_exact_col:
            add_score(table.name, cost_model.exact_column, "exact_column_match")
        elif has_overlap_col:
            add_score(table.name, cost_model.column_token_overlap, "column_token_overlap")
            
    # Apply Relationship-aware Expansion
    if include_related_tables:
        base_selected = [t for t in table_scores.keys() if table_scores[t] > 0]
        for t_name in base_selected:
            for rel in schema.relationships:
                if probe is not None:
                    probe.incr("related_expansion")
                if rel.source_table == t_name or rel.target_table == t_name:
                    neighbor = rel.target_table if rel.source_table == t_name else rel.source_table
                    
                    if rel.relationship_type in (RelationshipType.EXPLICIT, RelationshipType.CUSTOM):
                        add_score(neighbor, cost_model.explicit_neighbor, f"explicit_neighbor_of_{t_name}")
                    elif rel.relationship_type == RelationshipType.IMPLICIT:
                        add_score(neighbor, cost_model.implicit_neighbor, f"implicit_neighbor_of_{t_name}")
                    # implicit_fuzzy is not trusted to expand by default
                        
    # Benefit-vs-cost budget selection (Sprint 28.3)
    col_counts = {t.name: len(t.columns) for t in schema.tables}
    fk_map = fk_counts(schema)

    def _cost(name: str) -> float:
        return table_cost(col_counts.get(name, 0), fk_map.get(name, 0), cost_model)

    def _density(name: str, benefit: float) -> float:
        c = _cost(name)
        return float("inf") if c <= 0 else benefit / c

    scored = [(n, s) for n, s in table_scores.items() if s > 0]
    forced = [(n, s) for n, s in scored if "exact_table_match" in table_reasons[n]]
    rest = [(n, s) for n, s in scored if "exact_table_match" not in table_reasons[n]]
    forced.sort(key=lambda ns: (-ns[1], ns[0]))
    rest.sort(key=lambda ns: (-_density(ns[0], ns[1]), _cost(ns[0]), ns[0]))

    selected_tables = []
    total_cost = 0.0
    budget_exhausted = False

    def _append(name: str, benefit: float):
        nonlocal total_cost
        c = _cost(name)
        selected_tables.append(SelectedTable(
            table_name=name, score=benefit, reasons=table_reasons[name], cost=c))
        total_cost += c

    for name, benefit in forced:
        if len(selected_tables) >= max_tables:
            break
        _append(name, benefit)  # exact-match focus guaranteed (ignores budget)

    for name, benefit in rest:
        if len(selected_tables) >= max_tables:
            break
        if total_cost + _cost(name) > cost_model.cost_budget:
            budget_exhausted = True
            continue
        _append(name, benefit)

    fallback_used = False
    fallback_strategy = None

    fallback_limit = None
    max_fallback_tables = None

    if not selected_tables:
        fallback_used = True
        fallback_strategy = "deterministic_bounded_fallback"
        sorted_all_tables = sorted([t.name for t in schema.tables])
        max_fallback_tables = 5
        fallback_limit = min(max_tables, max_fallback_tables)
        for t_name in sorted_all_tables[:fallback_limit]:
            c = _cost(t_name)
            selected_tables.append(SelectedTable(table_name=t_name, score=0.1, reasons=["fallback"], cost=c))
            total_cost += c

    focus_tables = [st.table_name for st in selected_tables]
    
    # Discover Join Paths among top tables
    join_paths = []
    join_search_truncated = False
    top_tables = focus_tables[:5] # Limit combinations to top 5
    for i in range(len(top_tables)):
        for j in range(i + 1, len(top_tables)):
            source = top_tables[i]
            target = top_tables[j]
            search = find_join_paths(
                schema,
                source,
                target,
                max_depth=3,
                max_paths=1,
                allow_fuzzy=False,
                node_budget=node_budget,
            )
            join_paths.extend(search.paths)
            join_search_truncated = join_search_truncated or search.budget_truncated
            
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
        join_paths=unique_paths,
        fallback_used=fallback_used,
        fallback_strategy=fallback_strategy,
        fallback_limit=fallback_limit,
        max_fallback_tables=max_fallback_tables,
        join_search_truncated=join_search_truncated,
        total_cost=total_cost,
        cost_budget=cost_model.cost_budget,
        budget_exhausted=budget_exhausted,
    )
