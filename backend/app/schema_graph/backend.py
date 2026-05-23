from abc import ABC, abstractmethod
from typing import Dict, Any, List

class SchemaGraphBackend(ABC):
    @abstractmethod
    def build_graph(self, schema: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def personalized_pagerank(self, seeds: Dict[str, float]) -> Dict[str, float]:
        pass

    @abstractmethod
    def shortest_path(self, source: str, target: str, weight: str = "cost") -> List[str]:
        pass

    @abstractmethod
    def top_neighbors(self, table: str, limit: int, min_weight: float) -> List[str]:
        pass
