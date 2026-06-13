from dataclasses import dataclass
from typing import Literal, Tuple

INTENT_EXTRACTION_VERSION = "intent_extraction_v1"

IntentType = Literal[
    "list",
    "aggregate",
    "comparison",
    "ranking",
    "count",
    "unknown",
]


@dataclass(frozen=True)
class IntentSignal:
    """
    Represents an extracted signal flag with a boolean value and an explicit reason.
    """
    name: str
    value: bool
    reason: str


@dataclass(frozen=True)
class QueryIntent:
    """
    Aggregates intent classification and extracted signals.
    """
    normalized_query: str
    intent_type: IntentType

    has_filter: bool
    has_aggregation: bool
    has_grouping: bool
    has_ordering: bool
    has_limit: bool
    requires_join: bool
    has_time_range: bool
    ambiguity_detected: bool

    signals: Tuple[IntentSignal, ...]


@dataclass(frozen=True)
class IntentExtractionResult:
    """
    Final output for query understanding step.
    Wraps the raw query and the query understanding intent metadata.
    """
    raw_query: str
    intent: QueryIntent
    extraction_version: str = INTENT_EXTRACTION_VERSION
