from app.query_understanding.intent_contract import IntentExtractionResult
from app.retrieval.token_budget_contract import TokenBudgetResult
from app.query_understanding.intent_context_bridge_contract import (
    IntentBoundContextItem,
    IntentContextBridgeResult,
    ContextRole,
    INTENT_CONTEXT_BRIDGE_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class IntentContextBridge:
    """
    Bridge to bind query understanding intent extraction results with
    token budget context items, assigning deterministic semantic roles.
    """
    def bind(
        self,
        intent_result: IntentExtractionResult,
        token_budget_result: TokenBudgetResult,
    ) -> IntentContextBridgeResult:
        # 1. Validation Checks
        if not intent_result.raw_query or not intent_result.raw_query.strip():
            raise EmbeddingNonRetryableError("Intent raw query cannot be empty.")
        if not intent_result.intent.normalized_query or not intent_result.intent.normalized_query.strip():
            raise EmbeddingNonRetryableError("Intent normalized query cannot be empty.")
        if not token_budget_result.query_text or not token_budget_result.query_text.strip():
            raise EmbeddingNonRetryableError("Token budget query text cannot be empty.")
        
        if intent_result.raw_query != token_budget_result.query_text:
            raise EmbeddingNonRetryableError(
                f"Query mismatch: Intent query '{intent_result.raw_query}' does not match "
                f"Token budget query '{token_budget_result.query_text}'"
            )

        # Validate included items
        seen_ids = set()
        for item in token_budget_result.included_items:
            if not item.id or not item.id.strip():
                raise EmbeddingNonRetryableError("Included item ID cannot be empty.")
            if item.id in seen_ids:
                raise EmbeddingNonRetryableError(f"Duplicate included item ID found: '{item.id}'")
            seen_ids.add(item.id)
            
            if not item.text or not item.text.strip():
                raise EmbeddingNonRetryableError(f"Included item '{item.id}' has empty text.")
            if item.estimated_tokens <= 0:
                raise EmbeddingNonRetryableError(
                    f"Included item '{item.id}' has invalid estimated tokens: {item.estimated_tokens}"
                )

        # 2. Binding and Role Assignment Logic
        bound_items = []
        first_table_encountered = False
        
        intent = intent_result.intent

        for item in token_budget_result.included_items:
            role: ContextRole = "supporting_context"
            reason = ""

            # Check single-role precedence rules
            if item.object_type == "relationship" and intent.requires_join:
                role = "join_candidate"
                reason = "Bound as join_candidate because query requires join and item is a relationship."
            elif item.object_type == "column" and intent.has_aggregation:
                role = "aggregation_candidate"
                reason = "Bound as aggregation_candidate because query has aggregation and item is a column."
            elif item.object_type == "column" and intent.has_grouping:
                role = "grouping_candidate"
                reason = "Bound as grouping_candidate because query has grouping and item is a column."
            elif item.object_type == "column" and intent.has_ordering:
                role = "ordering_candidate"
                reason = "Bound as ordering_candidate because query has ordering/ranking and item is a column."
            elif item.object_type == "column" and intent.has_filter:
                role = "filter_candidate"
                reason = "Bound as filter_candidate because query has filter and item is a column."
            elif item.object_type == "table":
                if not first_table_encountered:
                    role = "primary_table"
                    reason = "Bound as primary_table because it is the first table in ranked context."
                    first_table_encountered = True
                else:
                    role = "supporting_context"
                    reason = "Bound as supporting_context table."
            else:
                role = "supporting_context"
                reason = f"Bound as supporting_context because it matches no specific rule for object type '{item.object_type}'."

            bound_item = IntentBoundContextItem(
                id=item.id,
                object_id=item.object_id,
                object_type=item.object_type,
                text=item.text,
                context_role=role,
                binding_reason=reason,
                estimated_tokens=item.estimated_tokens,
                retrieval_score=item.retrieval_score,
                ranking_score=item.ranking_score,
                rank=item.rank,
                source_candidate_rank=item.source_candidate_rank,
                selection_reason=item.selection_reason,
                summary_version=item.summary_version,
                schema_hash=item.schema_hash,
                provider_id=item.provider_id,
                model_id=item.model_id,
                dimension=item.dimension
            )
            bound_items.append(bound_item)

        # Excluded items list
        excluded_ids = [item.id for item in token_budget_result.excluded_items]

        return IntentContextBridgeResult(
            raw_query=intent_result.raw_query,
            normalized_query=intent.normalized_query,
            intent_type=intent.intent_type,
            has_filter=intent.has_filter,
            has_aggregation=intent.has_aggregation,
            has_grouping=intent.has_grouping,
            has_ordering=intent.has_ordering,
            has_limit=intent.has_limit,
            requires_join=intent.requires_join,
            has_time_range=intent.has_time_range,
            ambiguity_detected=intent.ambiguity_detected,
            bound_items=tuple(bound_items),
            excluded_item_ids=tuple(excluded_ids),
            bridge_version=INTENT_CONTEXT_BRIDGE_VERSION
        )
