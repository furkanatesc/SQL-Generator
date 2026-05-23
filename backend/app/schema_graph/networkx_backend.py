import math
import logging
from typing import Dict, Any, List
from .backend import SchemaGraphBackend

logger = logging.getLogger("schema_graph.networkx_backend")

class NetworkXGraphBackend(SchemaGraphBackend):
    def __init__(self):
        try:
            import networkx as nx
            self.nx = nx
        except ImportError:
            raise ImportError("NetworkX is required for NetworkXGraphBackend. Please install it using 'pip install networkx'")
        self.G = None

    def build_graph(self, schema: Dict[str, Any]) -> None:
        self.G = self.nx.DiGraph()
        
        tables = schema.get("tables", {})
        edges = schema.get("graph", {}).get("edges", [])
        
        degrees = {}
        for edge in edges:
            u, v = edge["source"], edge["target"]
            degrees[u] = degrees.get(u, 0) + 1
            degrees[v] = degrees.get(v, 0) + 1

        for table in tables.keys():
            self.G.add_node(table)
            
        for edge in edges:
            u = edge["source"]
            v = edge["target"]
            
            weight = 1.0
            
            # Hub penalty
            target_degree = degrees.get(v, 0)
            if target_degree > 0:
                degree_penalty = 1 / math.log(2 + target_degree)
                weight *= degree_penalty
                
            cost = -math.log(weight + 1e-9)
            if not self.G.has_edge(u, v):
                self.G.add_edge(u, v, weight=weight, cost=cost)

    def personalized_pagerank(self, seeds: Dict[str, float]) -> Dict[str, float]:
        if not self.G or not seeds:
            return {}
            
        total_score = sum(seeds.values())
        if total_score == 0:
            return {}
            
        personalization = {k: v / total_score for k, v in seeds.items()}
        
        for node in self.G.nodes():
            if node not in personalization:
                personalization[node] = 0.0
                
        try:
            return self.nx.pagerank(self.G, alpha=0.85, personalization=personalization, weight='weight')
        except Exception as e:
            logger.error(f"PPR calculation failed: {e}")
            return {}

    def shortest_path(self, source: str, target: str, weight: str = "cost") -> List[str]:
        if not self.G:
            return []
        try:
            undirected_G = self.G.to_undirected()
            return self.nx.shortest_path(undirected_G, source=source, target=target, weight=weight)
        except self.nx.NetworkXNoPath:
            return []
        except Exception as e:
            logger.error(f"Shortest path failed: {e}")
            return []

    def top_neighbors(self, table: str, limit: int, min_weight: float) -> List[str]:
        if not self.G or table not in self.G:
            return []
        
        neighbors = []
        for n in self.G.to_undirected().neighbors(table):
            edge_data = self.G.get_edge_data(table, n) or self.G.get_edge_data(n, table)
            if edge_data and edge_data.get("weight", 0) >= min_weight:
                neighbors.append((n, edge_data.get("weight", 0)))
                
        neighbors.sort(key=lambda x: x[1], reverse=True)
        return [n for n, w in neighbors[:limit]]
