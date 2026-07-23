"""Sprint 27.3 — feedback taksonomisi değerleri sabittir (27.2 StrEnum deseni)."""
from app.feedback import FeedbackVerdict, FeedbackCategory


def test_verdict_degerleri_sabit():
    assert FeedbackVerdict.CORRECT.value == "correct"
    assert FeedbackVerdict.INCORRECT.value == "incorrect"
    assert {v.value for v in FeedbackVerdict} == {"correct", "incorrect"}


def test_category_degerleri_sabit():
    assert {c.value for c in FeedbackCategory} == {
        "wrong_table", "wrong_column", "wrong_filter", "wrong_join",
        "wrong_aggregation", "wrong_order_limit", "other",
    }


def test_strenum_semantigi():
    # StrEnum üyesi str alt-tipidir ama tam `str` değildir; .value tam str'dir.
    # (27.2 error taksonomisiyle aynı sınır davranışı.)
    assert type(FeedbackCategory.OTHER) is not str
    assert type(FeedbackCategory.OTHER.value) is str
    assert FeedbackCategory.OTHER == "other"
