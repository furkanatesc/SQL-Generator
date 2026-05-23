from dataclasses import dataclass
from typing import List
import logging
from app.database import get_db_connection
from app.nlp.text_normalizer import TextNormalizer

@dataclass
class SynonymRule:
    term: str
    normalized_term: str
    target_type: str
    target_name: str
    confidence: float
    source: str
    priority: int


class SynonymRepository:
    def __init__(self, normalizer: TextNormalizer = None):
        self.normalizer = normalizer or TextNormalizer()

    def lookup(self, term: str) -> List[SynonymRule]:
        raise NotImplementedError


class StaticSynonymRepository(SynonymRepository):
    """
    Hızlı başlangıç ve bootstrap için veritabanı bağlantısı olmayan statik depo.
    """
    def __init__(self, normalizer: TextNormalizer = None):
        super().__init__(normalizer)
        self.rules = [
            SynonymRule('hekim', 'hekim', 'concept', 'doktor', 0.95, 'manual', 10),
            SynonymRule('doktor', 'doktor', 'concept', 'doktor', 0.95, 'manual', 10),
            SynonymRule('dr', 'dr', 'concept', 'doktor', 0.90, 'manual', 20),
            SynonymRule('branş', 'brans', 'concept', 'brans', 0.90, 'manual', 10),
            SynonymRule('uzmanlık', 'uzmanlik', 'concept', 'brans', 0.85, 'manual', 20),
            SynonymRule('hasta', 'hasta', 'concept', 'hasta', 0.95, 'manual', 10),
            SynonymRule('ver', 'ver', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
            SynonymRule('getir', 'getir', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
            SynonymRule('listele', 'listele', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
            SynonymRule('bana', 'bana', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('olan', 'olan', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('ile', 'ile', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('ve', 've', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('veya', 'veya', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('için', 'icin', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('tum', 'tum', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('tüm', 'tum', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('sorgu', 'sorgu', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('sorguyu', 'sorguyu', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('tablo', 'tablo', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('kayıt', 'kayit', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('bilgi', 'bilgi', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
            SynonymRule('sayısı', 'sayisi', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
            SynonymRule('sayisi', 'sayisi', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
            SynonymRule('toplam', 'toplam', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
            SynonymRule('ortalama', 'ortalama', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
        ]

    def lookup(self, term: str) -> List[SynonymRule]:
        normalized = self.normalizer.normalize(term)
        results = [r for r in self.rules if r.normalized_term == normalized]
        # Sort by priority ascending, then confidence descending
        results.sort(key=lambda x: (x.priority, -x.confidence))
        return results


class HybridSynonymRepository(SynonymRepository):
    """
    Production v1: Hem SQLite hem Statik kuralları birleştiren, hata anında statik kurallarla hayatta kalan repo.
    """
    def __init__(self, normalizer: TextNormalizer = None):
        super().__init__(normalizer)
        self.static_repo = StaticSynonymRepository(normalizer=self.normalizer)
        self.logger = logging.getLogger("synonym_repository")
        
    def lookup(self, term: str) -> List[SynonymRule]:
        static_rules = self.static_repo.lookup(term)
        db_rules = []
        
        normalized = self.normalizer.normalize(term)
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT term, normalized_term, target_type, target_name, confidence, source, priority
                    FROM synonym_rules
                    WHERE normalized_term = ? AND enabled = 1
                    """,
                    (normalized,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    db_rules.append(SynonymRule(
                        term=row["term"],
                        normalized_term=row["normalized_term"],
                        target_type=row["target_type"],
                        target_name=row["target_name"],
                        confidence=row["confidence"],
                        source=row["source"],
                        priority=row["priority"]
                    ))
        except Exception as e:
            self.logger.error(f"HybridSynonymRepository DB lookup failed: {e}")
            # Fallback to static, do nothing about the error
            
        all_rules = static_rules + db_rules
        
        # Deduplicate
        dedup_map = {}
        for r in all_rules:
            key = (r.normalized_term, r.target_type, r.target_name)
            if key not in dedup_map:
                dedup_map[key] = r
            else:
                existing = dedup_map[key]
                # Lower priority is better. If same, higher confidence is better.
                if r.priority < existing.priority or (r.priority == existing.priority and r.confidence > existing.confidence):
                    dedup_map[key] = r
                    
        results = list(dedup_map.values())
        results.sort(key=lambda x: (x.priority, -x.confidence))
        
        return results
