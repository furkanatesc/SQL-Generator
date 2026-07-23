"""Feedback taksonomisi (Sprint 27.3) — kullanıcı feedback'inin semantik ekseni.

Yaprak katman: stdlib dışına import YOKTUR. app.api ve 27.9 tüketicisi bunu
FastAPI/DB yüklemeden güvenle import eder (app.errors ile aynı disiplin).

Bu eksen 27.2'nin sistem/pipeline hata taksonomisinden FARKLIDIR: burada SQL
başarıyla üretilmiştir ama semantik olarak yanlış olabilir; kategori nesinin
yanlış olduğunu yakalar.
"""
from enum import StrEnum


class FeedbackVerdict(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class FeedbackCategory(StrEnum):
    WRONG_TABLE = "wrong_table"
    WRONG_COLUMN = "wrong_column"
    WRONG_FILTER = "wrong_filter"
    WRONG_JOIN = "wrong_join"
    WRONG_AGGREGATION = "wrong_aggregation"
    WRONG_ORDER_LIMIT = "wrong_order_limit"
    OTHER = "other"
