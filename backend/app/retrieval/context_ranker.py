from typing import Protocol, Tuple, List
from app.retrieval.retrieval_contract import TopKRetrievalResult
from app.retrieval.context_ranking_contract import (
    ContextRankingConfig,
    RankedContextItem,
    RankedContextResult
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

# Policy constants to avoid magic numbers in implementation
RELATIONSHIP_BONUS = 0.05
TABLE_BONUS = 0.03
COLUMN_BONUS = 0.00


class ContextRanker(Protocol):
    """
    Protocol defining the contract for context ranking backends.
    """
    def rank(
        self,
        result: TopKRetrievalResult,
        config: ContextRankingConfig
    ) -> RankedContextResult:
        """
        Ranks top-K candidates into prompt context items.
        """
        ...


class DeterministicContextRanker:
    """
    Deterministic implementation of the ContextRanker protocol.
    Runs entirely offline and ranks retrieval candidates using explicit rule bonuses.
    """
    def rank(
        self,
        result: TopKRetrievalResult,
        config: ContextRankingConfig
    ) -> RankedContextResult:
        # 1. Validations
        if config.max_candidates <= 0:
            raise EmbeddingNonRetryableError(
                f"max_candidates must be greater than zero, got config.max_candidates={config.max_candidates}"
            )

        # Check for duplicate candidate IDs
        seen_ids = set()
        for cand in result.candidates:
            if cand.id in seen_ids:
                raise EmbeddingNonRetryableError(
                    f"Duplicate candidate ID detected in TopKRetrievalResult: {cand.id}"
                )
            seen_ids.add(cand.id)

        # If empty candidates list, return empty result
        if not result.candidates:
            return RankedContextResult(
                query_text=result.query_text,
                items=()
            )

        # 2. Filter candidates below min_score (if min_score is specified)
        filtered_candidates = result.candidates
        if config.min_score is not None:
            filtered_candidates = [
                c for c in filtered_candidates if c.score >= config.min_score
            ]

        # 3. Calculate ranking_score and selection reason
        ranked_items = []
        for cand in filtered_candidates:
            if cand.object_type == "relationship":
                bonus = RELATIONSHIP_BONUS
                reason = f"Relationship matched (boosted by +{RELATIONSHIP_BONUS})"
            elif cand.object_type == "table":
                bonus = TABLE_BONUS
                reason = f"Table matched (boosted by +{TABLE_BONUS})"
            elif cand.object_type == "column":
                bonus = COLUMN_BONUS
                # Parse parent table from object_id
                if "." in cand.object_id:
                    parent_table = cand.object_id.split(".", 1)[0]
                else:
                    parent_table = "unknown"
                reason = f"Column matched (parent table: {parent_table})"
            else:
                raise EmbeddingNonRetryableError(
                    f"Unknown object type in candidate: {cand.object_type}"
                )

            ranking_score = cand.score + bonus
            
            # Temporary item holding all required values
            ranked_items.append((ranking_score, cand, reason))

        # 4. Deterministic Sort: ranking_score DESC, retrieval_score DESC, id ASC
        ranked_items.sort(key=lambda item: (-item[0], -item[1].score, item[1].id))

        # 5. Limit to max_candidates
        selected_items = ranked_items[:config.max_candidates]

        # 6. Convert to RankedContextItem DTOs
        final_items = []
        for rank_idx, (ranking_score, cand, reason) in enumerate(selected_items):
            final_items.append(RankedContextItem(
                id=cand.id,
                object_id=cand.object_id,
                object_type=cand.object_type,
                text=cand.text,
                retrieval_score=cand.score,
                ranking_score=ranking_score,
                rank=rank_idx + 1,
                selection_reason=reason,
                source_candidate_rank=cand.rank,
                summary_version=cand.summary_version,
                schema_hash=cand.schema_hash,
                provider_id=cand.provider_id,
                model_id=cand.model_id,
                dimension=cand.dimension
            ))

        return RankedContextResult(
            query_text=result.query_text,
            items=tuple(final_items)
        )
