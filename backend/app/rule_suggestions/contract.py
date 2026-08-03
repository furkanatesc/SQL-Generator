"""Feedback -> kural onerisi sozlesmesi — frozen record'lar (Sprint 27.9).

to_payload() JSON-safe ve DETERMINISTIKTIR: tuple'lar listeye, sozluk anahtarlari
SIRALI serilenir. Duvar-saati YOKTUR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

RULE_SUGGESTIONS_CONTRACT_VERSION = "rule_suggestions_v1"


def _sorted_int_map(d: Mapping[str, int]) -> dict:
    return {k: d[k] for k in sorted(d)}


@dataclass(frozen=True)
class SuggestionWindow:
    created_after: Optional[str]
    created_before: Optional[str]
    feedback_count: int
    eligible_count: int
    suggestion_count: int
    truncated: bool
    scan_cap: int

    def to_payload(self) -> dict:
        return {
            "created_after": self.created_after,
            "created_before": self.created_before,
            "feedback_count": self.feedback_count,
            "eligible_count": self.eligible_count,
            "suggestion_count": self.suggestion_count,
            "truncated": self.truncated,
            "scan_cap": self.scan_cap,
        }


@dataclass(frozen=True)
class RuleSuggestion:
    natural_query: str
    suggested_sql: str
    kind: str
    categories: Tuple[str, ...]
    support_count: int
    feedback_ids: Tuple[str, ...]
    job_ids: Tuple[str, ...]

    def to_payload(self) -> dict:
        return {
            "natural_query": self.natural_query,
            "suggested_sql": self.suggested_sql,
            "kind": self.kind,
            "categories": list(self.categories),
            "support_count": self.support_count,
            "feedback_ids": list(self.feedback_ids),
            "job_ids": list(self.job_ids),
        }


@dataclass(frozen=True)
class IneligibleSummary:
    total: int
    reasons: Mapping[str, int]

    def to_payload(self) -> dict:
        return {"total": self.total, "reasons": _sorted_int_map(self.reasons)}


@dataclass(frozen=True)
class RuleSuggestionsReport:
    version: str
    window: SuggestionWindow
    suggestions: Tuple[RuleSuggestion, ...]
    by_kind: Mapping[str, int]
    by_category: Mapping[str, int]
    ineligible: IneligibleSummary

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "window": self.window.to_payload(),
            "suggestions": [s.to_payload() for s in self.suggestions],
            "by_kind": _sorted_int_map(self.by_kind),
            "by_category": _sorted_int_map(self.by_category),
            "ineligible": self.ineligible.to_payload(),
        }
