"""Feedback taksonomisi (Sprint 27.3) — tek doğruluk kaynağı.

Yaprak katman: stdlib dışına import YOKTUR. app.api ve 27.9 bunu güvenle import eder.
"""
from app.feedback.categories import FeedbackCategory, FeedbackVerdict

__all__ = [
    "FeedbackCategory",
    "FeedbackVerdict",
]
