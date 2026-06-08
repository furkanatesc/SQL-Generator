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
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: RelationshipType
    confidence: float | None = None
    reason: str | None = None

class JoinPathCandidate(BaseModel):
    tables: list[str]
    edges: list[JoinPathEdge]
    total_score: float
    min_confidence: float | None = None
    path_length: int


def _edge_sort_key(edge: JoinPathEdge) -> str:
    return (
        f"{edge.source_table}.{edge.source_column}"
        f"->{edge.target_table}.{edge.target_column}"
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
    Prioritizes explicit paths over implicit.
    """
    
    # Precompute an adjacency list for O(1) neighbors lookup
    # adjacency[table_name] = list of RelationshipSchema edges starting from table_name
    adjacency: dict[str, list] = {t.name: [] for t in schema.tables}
    for rel in schema.relationships:
        if rel.relationship_type == RelationshipType.DISABLED:
            continue
        if not allow_fuzzy and rel.relationship_type == RelationshipType.IMPLICIT_FUZZY:
            continue
            
        if rel.source_table in adjacency:
            adjacency[rel.source_table].append(rel)
        if rel.target_table in adjacency:
            # Add reverse edge for traversal
            adjacency[rel.target_table].append(rel)
            
    all_paths = []

    def dfs(current_table: str, path_tables: list[str], path_edges: list[JoinPathEdge]):
        if current_table == target_table:
            # Calculate scores
            total_score = 0.0
            min_conf = None
            for e in path_edges:
                base_priority = RELATIONSHIP_TYPE_PRIORITY.get(e.relationship_type, 0)
                conf = e.confidence if e.confidence is not None else 1.0
                total_score += base_priority * conf
                
                if min_conf is None or conf < min_conf:
                    min_conf = conf

            all_paths.append(JoinPathCandidate(
                tables=list(path_tables),
                edges=list(path_edges),
                total_score=total_score,
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
                
            # Create the edge correctly oriented according to traversal direction
            if rel.source_table == current_table:
                src_tbl, src_col = rel.source_table, rel.source_column
                tgt_tbl, tgt_col = rel.target_table, rel.target_column
            else:
                src_tbl, src_col = rel.target_table, rel.target_column
                tgt_tbl, tgt_col = rel.source_table, rel.source_column
                
            jp_edge = JoinPathEdge(
                source_table=src_tbl,
                source_column=src_col,
                target_table=tgt_tbl,
                target_column=tgt_col,
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
    
    # Sort the paths: (-total_score, path_length, lexical_key)
    all_paths.sort(
        key=lambda path: (
            -path.total_score,
            path.path_length,
            "|".join(_edge_sort_key(edge) for edge in path.edges)
        )
    )

    return all_paths[:max_paths]
