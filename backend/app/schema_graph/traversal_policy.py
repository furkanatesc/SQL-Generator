from dataclasses import dataclass

@dataclass
class TraversalPolicy:
    min_candidate_score: float = 0.45
    min_edge_weight: float = 0.50
    max_depth: int = 2
    max_neighbors_per_seed: int = 5
    exclude_hubs: bool = True
    allow_hubs_as_connectors: bool = False
    token_budget: int = 6000
    max_tables: int = 30
    path_mode: str = "undirected_weighted"
