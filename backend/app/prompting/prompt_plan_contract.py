from dataclasses import dataclass
from typing import Literal, Tuple

PROMPT_PLAN_VERSION = "prompt_plan_v1"

PromptSectionType = Literal[
    "system_instructions",
    "user_intent",
    "schema_context",
    "relationship_context",
    "constraints",
    "output_contract",
]


@dataclass(frozen=True)
class PromptPlanSection:
    """
    DTO representing an individual structured section inside the prompt plan.
    """
    section_type: PromptSectionType
    title: str
    content_items: Tuple[str, ...]
    source_item_ids: Tuple[str, ...]
    required: bool


@dataclass(frozen=True)
class PromptPlanResult:
    """
    DTO representing the final structured prompt plan.
    Specifies sections to include, their order, and content items.
    """
    raw_query: str
    normalized_query: str
    intent_type: str

    sections: Tuple[PromptPlanSection, ...]

    plan_version: str = PROMPT_PLAN_VERSION
