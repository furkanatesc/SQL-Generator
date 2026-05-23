from dataclasses import dataclass

@dataclass
class TraversalPolicy:
    max_depth: int = 2
    max_neighbors_per_seed: int = 5
    min_edge_score: float = 0.50
    exclude_hubs: bool = True
    token_budget: int = 6000
