from app.prompting.prompt_plan_contract import PromptPlanResult
from app.prompting.prompt_render_contract import (
    RenderedPromptSection,
    RenderedPromptResult,
    PROMPT_RENDER_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class PromptRenderer:
    """
    Renderer that compiles a PromptPlanResult into a RenderedPromptResult.
    Performs fail-fast validations on section order, requirements, duplicates, and renders
    sections using a deterministic markdown bullet list format.
    """
    def __init__(self) -> None:
        self.expected_order = [
            "system_instructions",
            "user_intent",
            "schema_context",
            "relationship_context",
            "constraints",
            "output_contract"
        ]
        self.allowed_sections = set(self.expected_order)

    def render(self, prompt_plan: PromptPlanResult) -> RenderedPromptResult:
        # 1. Basic Fields Validation
        if not prompt_plan.raw_query or not prompt_plan.raw_query.strip():
            raise EmbeddingNonRetryableError("Raw query cannot be empty.")
        if not prompt_plan.normalized_query or not prompt_plan.normalized_query.strip():
            raise EmbeddingNonRetryableError("Normalized query cannot be empty.")
        if not prompt_plan.intent_type or not prompt_plan.intent_type.strip():
            raise EmbeddingNonRetryableError("Intent type cannot be empty.")
        
        if not prompt_plan.sections:
            raise EmbeddingNonRetryableError("Prompt plan sections cannot be empty.")

        # 2. Structural & Order Validation
        seen_types = set()
        actual_order = []

        for idx, section in enumerate(prompt_plan.sections):
            if not section.section_type:
                raise EmbeddingNonRetryableError("Section type cannot be empty.")
            if section.section_type in seen_types:
                raise EmbeddingNonRetryableError(f"Duplicate section type found: '{section.section_type}'")
            if section.section_type not in self.allowed_sections:
                raise EmbeddingNonRetryableError(f"Unknown section type found: '{section.section_type}'")
            seen_types.add(section.section_type)
            actual_order.append(section.section_type)

            if not section.title or not section.title.strip():
                raise EmbeddingNonRetryableError(f"Section '{section.section_type}' has empty title.")
            
            if not isinstance(section.source_item_ids, tuple):
                raise EmbeddingNonRetryableError(f"Section '{section.section_type}' source_item_ids must be a tuple.")
            if not isinstance(section.content_items, tuple):
                raise EmbeddingNonRetryableError(f"Section '{section.section_type}' content_items must be a tuple.")

            # Required section content check (relationship_context can be empty, others must not be)
            if section.required:
                if section.section_type == "relationship_context":
                    pass
                else:
                    if not section.content_items:
                        raise EmbeddingNonRetryableError(
                            f"Required section '{section.section_type}' has no content items."
                        )

        if actual_order != self.expected_order:
            raise EmbeddingNonRetryableError(
                f"Invalid section order: expected {self.expected_order}, got {actual_order}"
            )

        # 3. Deterministic Rendering
        rendered_sections = []
        section_texts = []

        for section in prompt_plan.sections:
            lines = [f"## {section.title}"]
            if section.content_items:
                lines.extend(f"- {item}" for item in section.content_items)
            rendered_text = "\n".join(lines)

            rendered_sec = RenderedPromptSection(
                section_type=section.section_type,
                title=section.title,
                rendered_text=rendered_text,
                source_item_ids=section.source_item_ids,
                required=section.required
            )
            rendered_sections.append(rendered_sec)
            section_texts.append(rendered_text)

        rendered_prompt = "\n\n".join(section_texts)

        return RenderedPromptResult(
            raw_query=prompt_plan.raw_query,
            normalized_query=prompt_plan.normalized_query,
            intent_type=prompt_plan.intent_type,
            rendered_prompt=rendered_prompt,
            rendered_sections=tuple(rendered_sections),
            prompt_render_version=PROMPT_RENDER_VERSION
        )
