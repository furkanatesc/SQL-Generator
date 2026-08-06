from collections import deque

from pydantic import BaseModel
from .schema_contract import DatabaseSchema, RelationshipType
from .relationship_priority import RELATIONSHIP_TYPE_PRIORITY

# Hub-table penalty is intentionally out of scope for Sprint 20.3.
# Future work: penalize high-degree tables during path scoring.

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


DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000


class JoinPathSearchResult(BaseModel):
    paths: list[JoinPathCandidate]
    budget_truncated: bool = False
    node_visits: int = 0
    node_budget: int
    branches_pruned: int = 0


def _hop_distances(adjacency, target):
    """Unweighted min-hop distance from every node to target over the (undirected) adjacency."""
    dist = {target: 0}
    q = deque([target])
    while q:
        node = q.popleft()
        for rel in adjacency.get(node, []):
            nbr = rel.target_table if rel.source_table == node else rel.source_table
            if nbr not in dist:
                dist[nbr] = dist[node] + 1
                q.append(nbr)
    return dist

def _edge_sort_key(edge: JoinPathEdge) -> str:
    return (
        f"{edge.from_table}.{edge.from_column}"
        f"->{edge.to_table}.{edge.to_column}"
    )

def _sort_paths(paths):
    paths.sort(key=lambda path: (
        -path.min_relationship_priority, -path.min_confidence,
        path.path_length, "|".join(_edge_sort_key(e) for e in path.edges)))

def find_join_paths(
    schema: DatabaseSchema,
    source_table: str,
    target_table: str,
    *,
    max_depth: int = 3,
    max_paths: int = 5,
    allow_fuzzy: bool = False,
    probe=None,
    node_budget: int = DEFAULT_JOIN_PATH_NODE_BUDGET,
) -> JoinPathSearchResult:
    """
    Finds valid join paths between source_table and target_table using cycle-safe DFS.
    Prioritizes explicit paths over implicit using a weakest-link scoring logic.
    """

    if max_paths <= 0:
        return JoinPathSearchResult(
            paths=[], budget_truncated=False, node_visits=0,
            node_budget=node_budget, branches_pruned=0)

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
            
    hop = _hop_distances(adjacency, target_table)
    src_hop = hop.get(source_table)
    if src_hop is None or src_hop > max_depth:
        return JoinPathSearchResult(
            paths=[], budget_truncated=False, node_visits=0,
            node_budget=node_budget, branches_pruned=0)

    stats = {"visits": 0, "pruned": 0}
    truncated = {"flag": False}

    kept = []
    worst_prefix = None  # (-min_pri, -min_conf, path_length) of worst kept when full

    def _record(cand):
        nonlocal worst_prefix
        kept.append(cand)
        if len(kept) > max_paths:
            _sort_paths(kept); kept.pop()
        if len(kept) == max_paths:
            _sort_paths(kept)
            w = kept[-1]
            worst_prefix = (-w.min_relationship_priority, -w.min_confidence, w.path_length)

    def dfs(current_table, path_tables, path_edges, pri_so_far, conf_so_far):
        if truncated["flag"]:
            return
        stats["visits"] += 1
        if probe is not None:
            probe.incr("dfs_visit")
        if stats["visits"] > node_budget:
            truncated["flag"] = True
            if probe is not None:
                probe.incr("join_budget_truncated")
            return
        if current_table == target_table:
            # completion uses path_edges (identical to pre-28.2)
            min_priority = 1000; min_conf = 1.0
            for e in path_edges:
                p = RELATIONSHIP_TYPE_PRIORITY.get(e.relationship_type, 0)
                if p < min_priority: min_priority = p
                c = e.confidence if e.confidence is not None else 1.0
                if c < min_conf: min_conf = c
            if probe is not None:
                probe.incr("path_recorded")
            _record(JoinPathCandidate(tables=list(path_tables), edges=list(path_edges),
                    min_relationship_priority=min_priority, min_confidence=min_conf,
                    path_length=len(path_edges)))
            return
        if len(path_edges) >= max_depth:
            return
        for rel in adjacency.get(current_table, []):
            if truncated["flag"]:
                return
            if probe is not None:
                probe.incr("adjacency_edge")
            next_table = rel.target_table if rel.source_table == current_table else rel.source_table
            if next_table in path_tables:
                continue
            nb_hop = hop.get(next_table)
            if nb_hop is None or (len(path_edges) + 1) + nb_hop > max_depth:
                stats["pruned"] += 1
                if probe is not None: probe.incr("branches_pruned")
                continue
            edge_priority = RELATIONSHIP_TYPE_PRIORITY.get(rel.relationship_type, 0)
            edge_conf = rel.confidence if rel.confidence is not None else 1.0
            new_pri = edge_priority if edge_priority < pri_so_far else pri_so_far
            new_conf = edge_conf if edge_conf < conf_so_far else conf_so_far
            if worst_prefix is not None:
                opt_prefix = (-new_pri, -new_conf, (len(path_edges) + 1) + nb_hop)
                if opt_prefix > worst_prefix:  # strictly worse -> cannot enter top-k
                    stats["pruned"] += 1
                    if probe is not None: probe.incr("branches_pruned")
                    continue
            # build edge (unchanged), recurse with running mins
            if rel.source_table == current_table:
                from_tbl, from_col = rel.source_table, rel.source_column
                to_tbl, to_col = rel.target_table, rel.target_column
            else:
                from_tbl, from_col = rel.target_table, rel.target_column
                to_tbl, to_col = rel.source_table, rel.source_column
            jp_edge = JoinPathEdge(
                from_table=from_tbl, from_column=from_col, to_table=to_tbl, to_column=to_col,
                relationship_source_table=rel.source_table, relationship_source_column=rel.source_column,
                relationship_target_table=rel.target_table, relationship_target_column=rel.target_column,
                relationship_type=rel.relationship_type, confidence=rel.confidence, reason=rel.reason)
            path_tables.append(next_table); path_edges.append(jp_edge)
            dfs(next_table, path_tables, path_edges, new_pri, new_conf)
            path_tables.pop(); path_edges.pop()

    dfs(source_table, [source_table], [], 1000, 1.0)
    _sort_paths(kept)
    return JoinPathSearchResult(
        paths=kept[:max_paths], budget_truncated=truncated["flag"], node_visits=stats["visits"],
        node_budget=node_budget, branches_pruned=stats["pruned"])
