import math
from typing import Protocol
from app.retrieval.context_ranking_contract import RankedContextResult
from app.retrieval.token_budget_contract import (
    TokenBudgetConfig,
    BudgetedContextItem,
    TokenBudgetResult,
    TOKEN_BUDGET_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class TokenEstimator(Protocol):
    """
    Protocol for estimating the token count of a given string.
    """
    def estimate(self, text: str) -> int:
        """
        Estimate the number of tokens in the text.
        
        Args:
            text: The text to estimate.
            
        Returns:
            The estimated token count.
            
        Raises:
            EmbeddingNonRetryableError: If the input text is invalid (e.g. empty).
        """
        ...


class SimpleTokenEstimator:
    """
    Simple, deterministic implementation of TokenEstimator.
    Estimates token count as ceil(word_count * 1.3).
    Fails fast on empty or whitespace-only strings.
    """
    def estimate(self, text: str) -> int:
        if not text or not text.strip():
            raise EmbeddingNonRetryableError("Empty text is not allowed for token estimation.")
        
        words = text.split()
        return math.ceil(len(words) * 1.3)


class TokenBudgetManager:
    """
    Manager to enforce a token budget on ranked context items.
    Controls prompt sizing deterministically and prevents context overflow.
    """
    def apply_budget(
        self,
        ranked_result: RankedContextResult,
        config: TokenBudgetConfig,
        estimator: TokenEstimator,
    ) -> TokenBudgetResult:
        # Enforce validation constraints
        if config.max_total_tokens <= 0:
            raise EmbeddingNonRetryableError(
                f"max_total_tokens must be greater than zero, got {config.max_total_tokens}"
            )
        if config.reserved_output_tokens < 0:
            raise EmbeddingNonRetryableError(
                f"reserved_output_tokens must be non-negative, got {config.reserved_output_tokens}"
            )
        if config.reserved_output_tokens >= config.max_total_tokens:
            raise EmbeddingNonRetryableError(
                f"reserved_output_tokens ({config.reserved_output_tokens}) must be less than max_total_tokens ({config.max_total_tokens})"
            )
        if config.truncation_strategy != "drop_lowest_ranked":
            raise EmbeddingNonRetryableError(
                f"Unsupported truncation strategy: {config.truncation_strategy}"
            )

        effective_context_budget = config.max_total_tokens - config.reserved_output_tokens
        used_context_tokens = 0
        
        included_items = []
        excluded_items = []
        
        # When an item exceeds remaining budget, subsequent items are also excluded
        budget_exhausted = False
        
        for item in ranked_result.items:
            est_tokens = estimator.estimate(item.text)
            
            if not budget_exhausted and (used_context_tokens + est_tokens <= effective_context_budget):
                budgeted_item = BudgetedContextItem(
                    id=item.id,
                    object_id=item.object_id,
                    object_type=item.object_type,
                    text=item.text,
                    estimated_tokens=est_tokens,
                    included=True,
                    exclusion_reason=None,
                    retrieval_score=item.retrieval_score,
                    ranking_score=item.ranking_score,
                    rank=item.rank,
                    source_candidate_rank=item.source_candidate_rank,
                    selection_reason=item.selection_reason,
                    summary_version=item.summary_version,
                    schema_hash=item.schema_hash,
                    provider_id=item.provider_id,
                    model_id=item.model_id,
                    dimension=item.dimension,
                )
                included_items.append(budgeted_item)
                used_context_tokens += est_tokens
            else:
                budget_exhausted = True
                budgeted_item = BudgetedContextItem(
                    id=item.id,
                    object_id=item.object_id,
                    object_type=item.object_type,
                    text=item.text,
                    estimated_tokens=est_tokens,
                    included=False,
                    exclusion_reason="exceeds_remaining_token_budget",
                    retrieval_score=item.retrieval_score,
                    ranking_score=item.ranking_score,
                    rank=item.rank,
                    source_candidate_rank=item.source_candidate_rank,
                    selection_reason=item.selection_reason,
                    summary_version=item.summary_version,
                    schema_hash=item.schema_hash,
                    provider_id=item.provider_id,
                    model_id=item.model_id,
                    dimension=item.dimension,
                )
                excluded_items.append(budgeted_item)
                
        return TokenBudgetResult(
            query_text=ranked_result.query_text,
            max_total_tokens=config.max_total_tokens,
            reserved_output_tokens=config.reserved_output_tokens,
            effective_context_budget=effective_context_budget,
            used_context_tokens=used_context_tokens,
            included_items=tuple(included_items),
            excluded_items=tuple(excluded_items),
            token_budget_version=TOKEN_BUDGET_VERSION,
        )
