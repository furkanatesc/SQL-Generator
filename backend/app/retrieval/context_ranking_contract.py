from dataclasses import dataclass
from typing import Literal, Tuple

ContextObjectType = Literal["table", "column", "relationship"]

CONTEXT_RANKING_VERSION = "context_ranking_v1"


@dataclass(frozen=True)
class ContextRankingConfig:
    """
    Configuration DTO for the context ranking process.
    Specifies constraints like maximum candidates to select,
    minimum retrieval similarity score, and flags for relationship
    or parent table inclusion.
    """
    max_candidates: int
    min_score: float | None = None
    include_relationships_for_selected_tables: bool = True
    include_parent_tables_for_columns: bool = True


@dataclass(frozen=True)
class RankedContextItem:
    """
    DTO representing a ranked and boosted schema context item,
    including separate retrieval and ranking scores, rank, selection reason,
    original candidate rank, and original embedding summary metadata.
    """
    id: str
    object_id: str
    object_type: ContextObjectType
    text: str
    retrieval_score: float
    ranking_score: float
    rank: int
    selection_reason: str
    source_candidate_rank: int
    summary_version: str
    schema_hash: str
    provider_id: str
    model_id: str
    dimension: int


@dataclass(frozen=True)
class RankedContextResult:
    """
    DTO grouping context ranking output items, including the query text
    and context ranking version metadata.
    """
    query_text: str
    items: Tuple[RankedContextItem, ...]
    context_ranking_version: str = CONTEXT_RANKING_VERSION
