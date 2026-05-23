from typing import Dict, Any, Set

class HubDetector:
    HUB_TOKENS = {
        "kullanici", "hastane", "kurum", "personel",
        "birim", "log", "parametre", "tanim", "yetki"
    }

    def __init__(self, p95_threshold_multiplier: float = 0.95):
        self.p95_threshold_multiplier = p95_threshold_multiplier

    def detect_hubs(self, schema: Dict[str, Any]) -> Set[str]:
        hubs = set()
        hubs |= self._known_name_hubs(schema)
        hubs |= self._token_hubs(schema)
        hubs |= self._degree_hubs(schema)
        return hubs

    def is_hub(self, table_name: str, schema: Dict[str, Any], cached_hubs: Set[str] = None) -> bool:
        if cached_hubs is not None:
            return table_name in cached_hubs
        return table_name in self.detect_hubs(schema)

    def _known_name_hubs(self, schema: Dict[str, Any]) -> Set[str]:
        exact_names = {t.upper() for t in self.HUB_TOKENS}
        tables = schema.get("tables", {}).keys()
        return {t for t in tables if t.upper() in exact_names}

    def _token_hubs(self, schema: Dict[str, Any]) -> Set[str]:
        tables = schema.get("tables", {}).keys()
        hubs = set()
        for t in tables:
            t_lower = t.lower()
            parts = t_lower.split('_')
            for part in parts:
                if part in self.HUB_TOKENS:
                    hubs.add(t)
                    break
        return hubs

    def _degree_hubs(self, schema: Dict[str, Any]) -> Set[str]:
        edges = schema.get("graph", {}).get("edges", [])
        if not edges:
            return set()
            
        degrees = {}
        for edge in edges:
            u, v = edge["source"], edge["target"]
            degrees[u] = degrees.get(u, 0) + 1
            degrees[v] = degrees.get(v, 0) + 1
            
        if not degrees:
            return set()
            
        sorted_degrees = sorted(degrees.values())
        p95_index = int(len(sorted_degrees) * self.p95_threshold_multiplier)
        if p95_index >= len(sorted_degrees):
            p95_index = len(sorted_degrees) - 1
            
        p95_degree = sorted_degrees[p95_index]
        
        min_hub_degree = max(p95_degree, 3)
            
        return {t for t, deg in degrees.items() if deg >= min_hub_degree}
