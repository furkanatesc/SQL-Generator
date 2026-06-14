import hashlib
from typing import Tuple
from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult
from app.prompting.few_shot_contract import SQLFewShotExampleSet
from app.prompting.example_selection_contract import (
    SQLExampleSelectionConfig,
    SQLExampleSelectionReason,
    SQLExampleSelectionResult,
    SQLExampleSelectionContractError,
    SQL_EXAMPLE_SELECTION_VERSION
)


class SQLExampleSelector:
    """
    Selector class that evaluates and selects SQL few-shot examples dynamically
    based on IntentContextBridgeResult intent features and config criteria.
    """

    def select_examples(
        self,
        bridge_result: IntentContextBridgeResult,
        example_set: SQLFewShotExampleSet,
        config: SQLExampleSelectionConfig
    ) -> SQLExampleSelectionResult:
        # 1. Validation checks
        if bridge_result is None:
            raise SQLExampleSelectionContractError("bridge_result cannot be None.")
        if example_set is None:
            raise SQLExampleSelectionContractError("example_set cannot be None.")
        if config is None:
            raise SQLExampleSelectionContractError("config cannot be None.")

        # Enforce required check
        if config.required and not example_set.examples:
            raise SQLExampleSelectionContractError(
                "Example set is empty but selection is configured as required."
            )

        # 2. Filter by dialect
        candidates = []
        rejected_by_dialect = []

        for ex in example_set.examples:
            if ex.dialect != config.target_dialect:
                rejected_by_dialect.append(ex.id)
            else:
                candidates.append(ex)

        # 3. Score candidates deterministically
        scored_candidates = []
        for ex in candidates:
            score = 0
            signals = []
            
            if ex.intent_type == bridge_result.intent_type:
                score += 100
                signals.append("intent_type_match")
            if "join" in ex.tags and bridge_result.requires_join:
                score += 20
                signals.append("join_match")
            if "aggregation" in ex.tags and bridge_result.has_aggregation:
                score += 20
                signals.append("aggregation_match")
            if "grouping" in ex.tags and bridge_result.has_grouping:
                score += 15
                signals.append("grouping_match")
            if "ordering" in ex.tags and bridge_result.has_ordering:
                score += 10
                signals.append("ordering_match")
            if "limit" in ex.tags and bridge_result.has_limit:
                score += 10
                signals.append("limit_match")
            if "time_range" in ex.tags and bridge_result.has_time_range:
                score += 10
                signals.append("time_range_match")

            scored_candidates.append({
                "example": ex,
                "score": score,
                "signals": tuple(signals)
            })

        # 4. Sorting & Tie-breaking: score DESC, id ASC
        scored_candidates.sort(key=lambda c: (-c["score"], c["example"].id))

        # 5. Slice & Select
        selected_candidates = scored_candidates[:config.max_examples]
        not_selected_candidates = scored_candidates[config.max_examples:]

        selected_examples = tuple(c["example"] for c in selected_candidates)
        selected_example_ids = tuple(ex.id for ex in selected_examples)

        # Construct selection reasons
        reasons = tuple(
            SQLExampleSelectionReason(
                example_id=c["example"].id,
                score=c["score"],
                matched_signals=c["signals"]
            )
            for c in selected_candidates
        )

        # Construct rejected examples list (dialect mismatched first, then lower-scored ones)
        rejected_example_ids = tuple(
            rejected_by_dialect + [c["example"].id for c in not_selected_candidates]
        )

        # 6. Compute selection fingerprint deterministically
        sorted_cand_ids = ",".join(sorted(ex.id for ex in example_set.examples))
        raw_str = (
            f"dialect:{config.target_dialect}|"
            f"max:{config.max_examples}|"
            f"req:{config.required}|"
            f"intent:{bridge_result.intent_type}|"
            f"join:{bridge_result.requires_join}|"
            f"agg:{bridge_result.has_aggregation}|"
            f"grp:{bridge_result.has_grouping}|"
            f"ord:{bridge_result.has_ordering}|"
            f"lim:{bridge_result.has_limit}|"
            f"time:{bridge_result.has_time_range}|"
            f"candidates:{sorted_cand_ids}"
        )
        fingerprint = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        return SQLExampleSelectionResult(
            target_dialect=config.target_dialect,
            intent_type=bridge_result.intent_type,
            selected_examples=selected_examples,
            selected_example_ids=selected_example_ids,
            rejected_example_ids=rejected_example_ids,
            selection_reasons=reasons,
            max_examples=config.max_examples,
            selection_fingerprint=fingerprint,
            version=SQL_EXAMPLE_SELECTION_VERSION
        )
