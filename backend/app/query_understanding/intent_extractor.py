import re
from typing import Protocol, List
from app.query_understanding.intent_contract import (
    IntentSignal,
    QueryIntent,
    IntentExtractionResult,
    IntentType,
    INTENT_EXTRACTION_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class IntentExtractor(Protocol):
    """
    Protocol defining the contract for query understanding intent extraction.
    """
    def extract(self, raw_query: str) -> IntentExtractionResult:
        """
        Extract intent classification and signals from the raw query.
        
        Args:
            raw_query: The natural-language query from the user.
            
        Returns:
            The extraction result containing normalized query and intent signals.
            
        Raises:
            EmbeddingNonRetryableError: If validation checks fail.
        """
        ...


class DeterministicRuleBasedIntentExtractor:
    """
    Offline, schema-agnostic implementation of IntentExtractor.
    Uses explicit keyword matching and heuristics to determine user intent.
    """
    def __init__(self, max_query_chars: int = 2000) -> None:
        self.max_query_chars = max_query_chars
        
        # Keyword Lists
        self.list_keywords = ["list", "show", "get", "find", "display"]
        self.count_keywords = ["count", "how many", "number of"]
        self.aggregate_keywords = ["sum", "total", "average", "avg", "min", "max"]
        self.ranking_keywords = ["top", "highest", "lowest", "most", "least", "best", "worst"]
        self.ordering_keywords = ["order by", "sort by", "sorted by", "sort", "sorted", "highest", "lowest", "latest", "earliest", "newest", "oldest"]
        self.time_range_keywords = ["today", "yesterday", "last week", "last month", "this year", "between", "before", "after", "since", "until"]
        
        self.filter_keywords = [
            "where", "with", "without", "unpaid", "paid", "active", "inactive", 
            "before", "after", "between", "greater than", "less than"
        ]
        
        self.comparison_keywords = ["greater than", "less than", "before", "after", "between"]
        
        self.ambiguity_keywords = ["some", "any", "maybe", "approximate", "about", "around", "similar", "etc", "or"]
        
        self.join_phrases = ["join", "joining", "and their", "for each", "together with"]
        self.join_connectors = ["with", "per", "by"]
        self.join_entities = [
            "customer", "customers", "order", "orders", "payment", "payments", 
            "product", "products", "employee", "employees", "user", "users", 
            "invoice", "invoices", "transaction", "transactions", "sale", "sales", 
            "department", "departments", "store", "stores"
        ]

    def _normalize(self, raw_query: str) -> str:
        """
        Normalizes query by stripping, collapsing spaces, and lowercasing.
        """
        # Collapse multiple spaces and trim
        normalized = " ".join(raw_query.split())
        return normalized.lower()

    def _find_matches(self, query: str, keywords: List[str]) -> List[str]:
        """
        Helper to find all matching keywords in query using word boundaries.
        """
        matched = []
        for word in keywords:
            # Handle multi-word boundary check
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, query):
                matched.append(word)
        return matched

    def extract(self, raw_query: str) -> IntentExtractionResult:
        # 1. Validation Checks
        if raw_query is None:
            raise EmbeddingNonRetryableError("Query cannot be None.")
        if not raw_query.strip():
            raise EmbeddingNonRetryableError("Query cannot be empty or whitespace-only.")
        if len(raw_query) > self.max_query_chars:
            raise EmbeddingNonRetryableError(
                f"Query length ({len(raw_query)}) exceeds maximum allowed length of {self.max_query_chars} characters."
            )
            
        normalized = self._normalize(raw_query)
        if not normalized:
            raise EmbeddingNonRetryableError("Normalized query is empty.")

        # 2. Extract Signals
        signals_list = []

        # Filter
        filter_matches = self._find_matches(normalized, self.filter_keywords)
        has_filter = len(filter_matches) > 0
        signals_list.append(IntentSignal(
            name="has_filter",
            value=has_filter,
            reason=f"Query contains filter keyword(s): {', '.join(filter_matches)}" if has_filter else ""
        ))

        # Aggregation (includes count keywords too, as count is an aggregation)
        agg_matches = self._find_matches(normalized, self.aggregate_keywords)
        cnt_matches = self._find_matches(normalized, self.count_keywords)
        has_aggregation = (len(agg_matches) > 0) or (len(cnt_matches) > 0)
        
        all_agg_matches = agg_matches + cnt_matches
        signals_list.append(IntentSignal(
            name="has_aggregation",
            value=has_aggregation,
            reason=f"Query contains aggregation keyword(s): {', '.join(all_agg_matches)}" if has_aggregation else ""
        ))

        # Grouping (Heuristic: group by, per <entity>, for each <entity>, or by <entity> when has_aggregation is True)
        has_grouping = False
        grouping_reason = ""
        entities_regex = "|".join(self.join_entities)
        
        if "group by" in normalized:
            has_grouping = True
            grouping_reason = "Query contains explicit 'group by'"
        elif re.search(rf"\bper\s+({entities_regex})\b", normalized):
            group_match = re.search(rf"\bper\s+({entities_regex})\b", normalized).group(0)
            has_grouping = True
            grouping_reason = f"Query contains grouping pattern: '{group_match}'"
        elif re.search(rf"\bfor each\s+({entities_regex})\b", normalized):
            group_match = re.search(rf"\bfor each\s+({entities_regex})\b", normalized).group(0)
            has_grouping = True
            grouping_reason = f"Query contains grouping pattern: '{group_match}'"
        elif has_aggregation and re.search(rf"\bby\s+({entities_regex})\b", normalized):
            group_match = re.search(rf"\bby\s+({entities_regex})\b", normalized).group(0)
            has_grouping = True
            grouping_reason = f"Query contains aggregate and grouping pattern: '{group_match}'"

        signals_list.append(IntentSignal(
            name="has_grouping",
            value=has_grouping,
            reason=grouping_reason
        ))

        # Ordering (Heuristic: order by keywords OR any matched ranking keywords)
        order_matches = self._find_matches(normalized, self.ordering_keywords)
        ranking_matches = self._find_matches(normalized, self.ranking_keywords)
        has_ordering = len(order_matches) > 0 or len(ranking_matches) > 0
        
        order_reason = ""
        if len(order_matches) > 0:
            order_reason = f"Query contains ordering keyword(s): {', '.join(order_matches)}"
        elif len(ranking_matches) > 0:
            order_reason = f"Query contains ranking/ordering keyword(s): {', '.join(ranking_matches)}"

        signals_list.append(IntentSignal(
            name="has_ordering",
            value=has_ordering,
            reason=order_reason
        ))

        # Limit (regex matches top/first/last/limit followed by a digit)
        limit_match = re.search(r"\b(top|first|last|limit)\s+\d+\b", normalized)
        has_limit = limit_match is not None
        signals_list.append(IntentSignal(
            name="has_limit",
            value=has_limit,
            reason=f"Query contains limit pattern: '{limit_match.group(0)}'" if has_limit else ""
        ))

        # Time range
        time_matches = self._find_matches(normalized, self.time_range_keywords)
        has_time_range = len(time_matches) > 0
        signals_list.append(IntentSignal(
            name="has_time_range",
            value=has_time_range,
            reason=f"Query contains time keyword(s): {', '.join(time_matches)}" if has_time_range else ""
        ))

        # Requires Join Heuristic
        join_phrases_matches = self._find_matches(normalized, self.join_phrases)
        join_connectors_matches = self._find_matches(normalized, self.join_connectors)
        entity_matches = self._find_matches(normalized, self.join_entities)
        
        requires_join = False
        join_reason = ""
        if len(join_phrases_matches) > 0:
            requires_join = True
            join_reason = f"Query contains explicit join phrase(s): {', '.join(join_phrases_matches)}"
        elif len(join_connectors_matches) > 0 and len(entity_matches) >= 2:
            requires_join = True
            join_reason = f"Query contains connector '{join_connectors_matches[0]}' and multiple entity terms: {', '.join(entity_matches)}"
            
        signals_list.append(IntentSignal(
            name="requires_join",
            value=requires_join,
            reason=join_reason if requires_join else ""
        ))

        # Ambiguity Detected
        ambig_matches = self._find_matches(normalized, self.ambiguity_keywords)
        ambiguity_detected = len(ambig_matches) > 0
        signals_list.append(IntentSignal(
            name="ambiguity_detected",
            value=ambiguity_detected,
            reason=f"Query contains ambiguity keyword(s): {', '.join(ambig_matches)}" if ambiguity_detected else ""
        ))

        # 3. Intent Classification (Precedence: ranking -> count -> aggregate -> list -> comparison -> unknown)
        ranking_matches = self._find_matches(normalized, self.ranking_keywords)
        
        intent_type: IntentType = "unknown"
        if len(ranking_matches) > 0:
            intent_type = "ranking"
        elif len(cnt_matches) > 0:
            intent_type = "count"
        elif len(agg_matches) > 0:
            intent_type = "aggregate"
        elif self._find_matches(normalized, self.list_keywords):
            intent_type = "list"
        elif self._find_matches(normalized, self.comparison_keywords):
            intent_type = "comparison"

        intent = QueryIntent(
            normalized_query=normalized,
            intent_type=intent_type,
            has_filter=has_filter,
            has_aggregation=has_aggregation,
            has_grouping=has_grouping,
            has_ordering=has_ordering,
            has_limit=has_limit,
            requires_join=requires_join,
            has_time_range=has_time_range,
            ambiguity_detected=ambiguity_detected,
            signals=tuple(signals_list)
        )

        return IntentExtractionResult(
            raw_query=raw_query,
            intent=intent,
            extraction_version=INTENT_EXTRACTION_VERSION
        )
