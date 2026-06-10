from pydantic import BaseModel
from .schema_contract import DatabaseSchema, RelationshipType

# Hub-table penalty is intentionally out of scope for Sprint 20.3.
# Future work: penalize high-degree tables during path scoring.

RELATIONSHIP_TYPE_PRIORITY = {
    RelationshipType.EXPLICIT: 100,
    RelationshipType.CUSTOM: 90,
    RelationshipType.IMPLICIT: 60,
    RelationshipType.IMPLICIT_FUZZY: 40,
}

class JoinPathEdge(BaseModel):
    """
    Traversal-oriented edge representing a single step in a join path.
    
    from_table / to_table represent the traversal direction during graph search.
    relationship_source_table / relationship_target_table represent the actual
    underlying foreign key ownership / schema contract, regardless of traversal direction.
    """
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    
    relationship_source_table: str
    relationship_source_column: str
    relationship_target_table: str
    relationship_target_column: str
    
    relationship_type: RelationshipType
    confidence: float | None = None
    reason: str | None = None

class JoinPathCandidate(BaseModel):
    tables: list[str]
    edges: list[JoinPathEdge]
    min_relationship_priority: int
    min_confidence: float
    path_length: int


def _edge_sort_key(edge: JoinPathEdge) -> str:
    return (
        f"{edge.from_table}.{edge.from_column}"
        f"->{edge.to_table}.{edge.to_column}"
    )

def find_join_paths(
    schema: DatabaseSchema,
    source_table: str,
    target_table: str,
    *,
    max_depth: int = 3,
    max_paths: int = 5,
    allow_fuzzy: bool = False,
) -> list[JoinPathCandidate]:
    """
    Finds valid join paths between source_table and target_table using cycle-safe DFS.
    Prioritizes explicit paths over implicit using a weakest-link scoring logic.
    """
    
    adjacency: dict[str, list] = {t.name: [] for t in schema.tables}
    for rel in schema.relationships:
        if rel.relationship_type == RelationshipType.DISABLED:
            continue
        if not allow_fuzzy and rel.relationship_type == RelationshipType.IMPLICIT_FUZZY:
            continue
            
        if rel.source_table in adjacency:
            adjacency[rel.source_table].append(rel)
        if rel.target_table in adjacency:
            adjacency[rel.target_table].append(rel)
            
    all_paths = []

    def dfs(current_table: str, path_tables: list[str], path_edges: list[JoinPathEdge]):
        if current_table == target_table:
            # Calculate weakest-link scores
            min_priority = 1000
            min_conf = 1.0
            
            for e in path_edges:
                priority = RELATIONSHIP_TYPE_PRIORITY.get(e.relationship_type, 0)
                if priority < min_priority:
                    min_priority = priority
                    
                conf = e.confidence if e.confidence is not None else 1.0
                if conf < min_conf:
                    min_conf = conf

            all_paths.append(JoinPathCandidate(
                tables=list(path_tables),
                edges=list(path_edges),
                min_relationship_priority=min_priority,
                min_confidence=min_conf,
                path_length=len(path_edges)
            ))
            return
            
        if len(path_edges) >= max_depth:
            return
            
        for rel in adjacency.get(current_table, []):
            next_table = rel.target_table if rel.source_table == current_table else rel.source_table
            
            if next_table in path_tables:
                # Cycle detected
                continue
                
            if rel.source_table == current_table:
                from_tbl, from_col = rel.source_table, rel.source_column
                to_tbl, to_col = rel.target_table, rel.target_column
            else:
                from_tbl, from_col = rel.target_table, rel.target_column
                to_tbl, to_col = rel.source_table, rel.source_column
                
            jp_edge = JoinPathEdge(
                from_table=from_tbl,
                from_column=from_col,
                to_table=to_tbl,
                to_column=to_col,
                relationship_source_table=rel.source_table,
                relationship_source_column=rel.source_column,
                relationship_target_table=rel.target_table,
                relationship_target_column=rel.target_column,
                relationship_type=rel.relationship_type,
                confidence=rel.confidence,
                reason=rel.reason
            )
            
            path_tables.append(next_table)
            path_edges.append(jp_edge)
            
            dfs(next_table, path_tables, path_edges)
            
            path_tables.pop()
            path_edges.pop()

    dfs(source_table, [source_table], [])
    
    # Sort the paths: (-min_priority, -min_conf, length, lexical_key)
    all_paths.sort(
        key=lambda path: (
            -path.min_relationship_priority,
            -path.min_confidence,
            path.path_length,
            "|".join(_edge_sort_key(edge) for edge in path.edges)
        )
    )

    return all_paths[:max_paths]
