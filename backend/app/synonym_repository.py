from dataclasses import dataclass
from typing import List
from app.database import get_db_connection

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
    def lookup(self, normalized_term: str) -> List[SynonymRule]:
        raise NotImplementedError


class StaticSynonymRepository(SynonymRepository):
    """
    Hızlı başlangıç ve bootstrap için veritabanı bağlantısı olmayan statik depo.
    """
    def __init__(self):
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

    def lookup(self, normalized_term: str) -> List[SynonymRule]:
        results = [r for r in self.rules if r.normalized_term == normalized_term]
        # Sort by priority ascending, then confidence descending
        results.sort(key=lambda x: (x.priority, -x.confidence))
        return results


class SQLiteSynonymRepository(SynonymRepository):
    """
    Production v1: SQLite veritabanı tabanlı eş anlamlılar ve override kuralları deposu.
    """
    def lookup(self, normalized_term: str) -> List[SynonymRule]:
        rules = []
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT term, normalized_term, target_type, target_name, confidence, source, priority
                    FROM synonym_rules
                    WHERE normalized_term = ? AND enabled = 1
                    ORDER BY priority ASC, confidence DESC
                    """,
                    (normalized_term,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    rules.append(SynonymRule(
                        term=row["term"],
                        normalized_term=row["normalized_term"],
                        target_type=row["target_type"],
                        target_name=row["target_name"],
                        confidence=row["confidence"],
                        source=row["source"],
                        priority=row["priority"]
                    ))
        except Exception as e:
            import logging
            logger = logging.getLogger("synonym_repository")
            logger.error(f"SQLiteSynonymRepository lookup failed: {e}")
            
        return rules
