from typing import Dict, Any, Set
from app.nlp.text_normalizer import TextNormalizer

class HubDetector:
    KNOWN_HUB_TABLES = {
        "KULLANICI", "HASTANE", "KURUM", "PERSONEL",
        "BIRIM", "LOG", "PARAMETRE", "TANIM", "YETKI"
    }
    
    HUB_TOKENS = {
        "kullanici", "hastane", "kurum", "personel",
        "birim", "log", "parametre", "tanim", "yetki"
    }

    def __init__(self, p95_threshold_multiplier: float = 0.95, normalizer: TextNormalizer = None):
        self.p95_threshold_multiplier = p95_threshold_multiplier
        self.normalizer = normalizer or TextNormalizer()

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
        tables = schema.get("tables", {}).keys()
        return {t for t in tables if t.upper() in self.KNOWN_HUB_TABLES}

    def _token_hubs(self, schema: Dict[str, Any]) -> Set[str]:
        tables = schema.get("tables", {}).keys()
        hubs = set()
        for t in tables:
            tokens = self.normalizer.tokenize(t)
            if tokens.intersection(self.HUB_TOKENS):
                hubs.add(t)
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
