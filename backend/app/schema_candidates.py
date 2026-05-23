from dataclasses import dataclass, field
from typing import Dict, Any, List

SOURCE_CAPS = {
    "exact_table_match": 1.00,
    "exact_table_qualifier": 1.00,
    "synonym_table_match": 0.90,
    "subset_table_match": 0.90,
    "schema_lexicon": 0.85,
    "value_index": 0.90,
    "rag": 0.65,
    "exact_column_match": 0.60,
    "keyword_table_match": 0.50,
    "keyword_column_match": 0.30,
}

@dataclass
class CandidateSignal:
    source: str
    score: float
    reason: str
    trace_data: Dict[str, Any] = None
    token: str = None

@dataclass
class CandidateAggregate:
    table: str
    signals: List[CandidateSignal] = field(default_factory=list)
    
    @property
    def score(self) -> float:
        by_source = {}
        for s in self.signals:
            by_source.setdefault(s.source, 0.0)
            by_source[s.source] = max(by_source[s.source], s.score)
            
        total = 0.0
        for source, max_score in by_source.items():
            cap = SOURCE_CAPS.get(source, 1.0)
            total += min(max_score, cap)
            
        return min(total, 1.0)
        
    def add_signal(self, signal: CandidateSignal):
        self.signals.append(signal)

    def to_dict(self):
        return {
            "table": self.table,
            "final_score": self.score,
            "signals": [
                {
                    "source": s.source,
                    "score": s.score,
                    "reason": s.reason,
                    "trace_data": s.trace_data,
                    "token": s.token
                } for s in self.signals
            ]
        }
