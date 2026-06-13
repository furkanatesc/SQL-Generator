from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult
from app.prompting.prompt_plan_contract import (
    PromptPlanSection,
    PromptPlanResult,
    PROMPT_PLAN_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class PromptPlanner:
    """
    Planner that deterministic constructs a PromptPlanResult from an IntentContextBridgeResult.
    Groups context items by role and packages system guidelines, user intents, schema,
    relationships, constraints, and output formats into structured plan sections.
    """
    def __init__(self) -> None:
        self.valid_roles = {
            "primary_table",
            "filter_candidate",
            "join_candidate",
            "ordering_candidate",
            "aggregation_candidate",
            "grouping_candidate",
            "supporting_context"
        }

    def plan(self, bridge_result: IntentContextBridgeResult) -> PromptPlanResult:
        # 1. Validation
        if not bridge_result.raw_query or not bridge_result.raw_query.strip():
            raise EmbeddingNonRetryableError("Raw query cannot be empty.")
        if not bridge_result.normalized_query or not bridge_result.normalized_query.strip():
            raise EmbeddingNonRetryableError("Normalized query cannot be empty.")
        if not bridge_result.intent_type or not bridge_result.intent_type.strip():
            raise EmbeddingNonRetryableError("Intent type cannot be empty.")

        seen_ids = set()
        for item in bridge_result.bound_items:
            if not item.id or not item.id.strip():
                raise EmbeddingNonRetryableError("Bound item ID cannot be empty.")
            if item.id in seen_ids:
                raise EmbeddingNonRetryableError(f"Duplicate bound item ID found: '{item.id}'")
            seen_ids.add(item.id)

            if not item.text or not item.text.strip():
                raise EmbeddingNonRetryableError(f"Bound item '{item.id}' has empty text.")
            if not item.binding_reason or not item.binding_reason.strip():
                raise EmbeddingNonRetryableError(f"Bound item '{item.id}' has empty binding reason.")
            if item.context_role not in self.valid_roles:
                raise EmbeddingNonRetryableError(
                    f"Bound item '{item.id}' has unknown context role: '{item.context_role}'"
                )

        # 2. Separate Context Items
        schema_items = []
        schema_ids = []
        relationship_items = []
        relationship_ids = []

        for item in bridge_result.bound_items:
            if item.context_role == "join_candidate":
                content = f"Relationship: {item.id} | Reason: {item.binding_reason} | Text: {item.text}"
                relationship_items.append(content)
                relationship_ids.append(item.id)
            else:
                content = f"Table/Column: {item.id} | Role: {item.context_role} | Reason: {item.binding_reason} | Text: {item.text}"
                schema_items.append(content)
                schema_ids.append(item.id)

        # 3. Build Deterministic Sections List
        sections = []

        # Section 1: system_instructions
        sections.append(PromptPlanSection(
            section_type="system_instructions",
            title="System Instructions",
            content_items=(
                "You are a SQL generation planner.",
                "Use only provided schema context.",
                "Do not invent tables or columns."
            ),
            source_item_ids=(),
            required=True
        ))

        # Section 2: user_intent
        sections.append(PromptPlanSection(
            section_type="user_intent",
            title="User Intent",
            content_items=(
                f"Intent Type: {bridge_result.intent_type}",
                f"Filters Required: {bridge_result.has_filter}",
                f"Aggregation Required: {bridge_result.has_aggregation}",
                f"Grouping Required: {bridge_result.has_grouping}",
                f"Ordering Required: {bridge_result.has_ordering}",
                f"Limit Required: {bridge_result.has_limit}",
                f"Joins Required: {bridge_result.requires_join}",
                f"Time Range Present: {bridge_result.has_time_range}",
                f"Ambiguity Detected: {bridge_result.ambiguity_detected}"
            ),
            source_item_ids=(),
            required=True
        ))

        # Section 3: schema_context
        sections.append(PromptPlanSection(
            section_type="schema_context",
            title="Schema Context",
            content_items=tuple(schema_items),
            source_item_ids=tuple(schema_ids),
            required=True
        ))

        # Section 4: relationship_context
        sections.append(PromptPlanSection(
            section_type="relationship_context",
            title="Relationship Context",
            content_items=tuple(relationship_items),
            source_item_ids=tuple(relationship_ids),
            required=True
        ))

        # Section 5: constraints
        sections.append(PromptPlanSection(
            section_type="constraints",
            title="Constraints",
            content_items=(
                "Use only listed tables and columns.",
                "Prefer explicit joins from relationship context.",
                "If required information is missing, do not invent it.",
                "Return only SQL in output stage."
            ),
            source_item_ids=(),
            required=True
        ))

        # Section 6: output_contract
        sections.append(PromptPlanSection(
            section_type="output_contract",
            title="Output Contract",
            content_items=(
                "Expected output: SQL string only.",
                "No markdown.",
                "No explanation."
            ),
            source_item_ids=(),
            required=True
        ))

        return PromptPlanResult(
            raw_query=bridge_result.raw_query,
            normalized_query=bridge_result.normalized_query,
            intent_type=bridge_result.intent_type,
            sections=tuple(sections),
            plan_version=PROMPT_PLAN_VERSION
        )
