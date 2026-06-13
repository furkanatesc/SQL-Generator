from dataclasses import dataclass
from typing import Literal, Tuple

TOKEN_BUDGET_VERSION = "token_budget_v1"

TruncationStrategy = Literal["drop_lowest_ranked"]


@dataclass(frozen=True)
class TokenBudgetConfig:
    """
    Configuration DTO for the token budget process.
    Specifies token limits, reserved response capacity, and truncation policy.
    """
    max_total_tokens: int
    reserved_output_tokens: int = 0
    truncation_strategy: TruncationStrategy = "drop_lowest_ranked"


@dataclass(frozen=True)
class BudgetedContextItem:
    """
    DTO representing a ranked context item after the token budget selection.
    Includes original metadata, ranking/retrieval scores, and budgeting decisions.
    """
    id: str
    object_id: str
    object_type: str
    text: str

    estimated_tokens: int
    included: bool
    exclusion_reason: str | None

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
class TokenBudgetResult:
    """
    DTO representing the output of the token budget manager.
    Bundles the context items that fit into the budget, those that were excluded,
    and metadata about token utilization.
    """
    query_text: str
    max_total_tokens: int
    reserved_output_tokens: int
    effective_context_budget: int
    used_context_tokens: int
    included_items: Tuple[BudgetedContextItem, ...]
    excluded_items: Tuple[BudgetedContextItem, ...]
    token_budget_version: str = TOKEN_BUDGET_VERSION
