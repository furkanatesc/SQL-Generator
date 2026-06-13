from dataclasses import dataclass
from typing import Literal, Tuple

INTENT_CONTEXT_BRIDGE_VERSION = "intent_context_bridge_v1"

ContextRole = Literal[
    "primary_table",
    "filter_candidate",
    "join_candidate",
    "ordering_candidate",
    "aggregation_candidate",
    "grouping_candidate",
    "supporting_context",
]


@dataclass(frozen=True)
class IntentBoundContextItem:
    """
    DTO representing a budgeted context item bound with a semantic role
    determined by the user query intent.
    """
    id: str
    object_id: str
    object_type: str
    text: str

    context_role: ContextRole
    binding_reason: str

    estimated_tokens: int
    retrieval_score: float
    ranking_score: float
    rank: int
    source_candidate_rank: int
    selection_reason: str

    summary_version: str
    schema_hash: str
    provider_id: str
    model_id: str
    dimension: int


@dataclass(frozen=True)
class IntentContextBridgeResult:
    """
    Unified DTO representing query intent combined with role-bound context items.
    """
    raw_query: str
    normalized_query: str
    intent_type: str

    has_filter: bool
    has_aggregation: bool
    has_grouping: bool
    has_ordering: bool
    has_limit: bool
    requires_join: bool
    has_time_range: bool
    ambiguity_detected: bool

    bound_items: Tuple[IntentBoundContextItem, ...]
    excluded_item_ids: Tuple[str, ...]

    bridge_version: str = INTENT_CONTEXT_BRIDGE_VERSION
