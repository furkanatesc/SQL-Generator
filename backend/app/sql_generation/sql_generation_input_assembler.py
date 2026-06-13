import hashlib
from app.prompting.prompt_render_contract import RenderedPromptResult
from app.sql_generation.sql_generation_input_contract import (
    SQLGenerationInputConfig,
    SQLGenerationConstraint,
    SQLGenerationInputResult,
    SQL_GENERATION_INPUT_VERSION
)
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


class SQLGenerationInputAssembler:
    """
    Assembler that deterministic constructs a SQLGenerationInputResult from
    a RenderedPromptResult and SQLGenerationInputConfig.
    """
    def __init__(self) -> None:
        self.allowed_dialects = {"sqlite", "postgresql", "oracle"}

    def assemble(
        self,
        rendered_prompt_result: RenderedPromptResult,
        config: SQLGenerationInputConfig
    ) -> SQLGenerationInputResult:
        # 1. Validate RenderedPromptResult fields
        if not rendered_prompt_result.raw_query or not rendered_prompt_result.raw_query.strip():
            raise EmbeddingNonRetryableError("Raw query cannot be empty.")
        if not rendered_prompt_result.normalized_query or not rendered_prompt_result.normalized_query.strip():
            raise EmbeddingNonRetryableError("Normalized query cannot be empty.")
        if not rendered_prompt_result.intent_type or not rendered_prompt_result.intent_type.strip():
            raise EmbeddingNonRetryableError("Intent type cannot be empty.")
        if not rendered_prompt_result.rendered_prompt or not rendered_prompt_result.rendered_prompt.strip():
            raise EmbeddingNonRetryableError("Rendered prompt cannot be empty.")
        
        if not rendered_prompt_result.rendered_sections:
            raise EmbeddingNonRetryableError("Rendered sections cannot be empty.")

        # Validate rendered sections
        for idx, section in enumerate(rendered_prompt_result.rendered_sections):
            if not section.section_type or not section.section_type.strip():
                raise EmbeddingNonRetryableError(f"Section at index {idx} has empty type.")
            if not section.title or not section.title.strip():
                raise EmbeddingNonRetryableError(f"Section at index {idx} has empty title.")
            if not section.rendered_text or not section.rendered_text.strip():
                raise EmbeddingNonRetryableError(f"Section at index {idx} has empty rendered text.")
            if not isinstance(section.source_item_ids, tuple):
                raise EmbeddingNonRetryableError(f"Section at index {idx} source_item_ids must be a tuple.")

        # 2. Validate Config
        if config.target_dialect not in self.allowed_dialects:
            raise EmbeddingNonRetryableError(f"Unsupported target dialect: '{config.target_dialect}'")
        if config.max_prompt_chars <= 0:
            raise EmbeddingNonRetryableError(f"max_prompt_chars must be positive, got {config.max_prompt_chars}")

        # 3. Validate Prompt Length
        prompt_len = len(rendered_prompt_result.rendered_prompt)
        if prompt_len > config.max_prompt_chars:
            raise EmbeddingNonRetryableError(
                f"Rendered prompt length ({prompt_len}) exceeds maximum limit ({config.max_prompt_chars})"
            )

        # 4. Hashing
        prompt_sha256 = hashlib.sha256(
            rendered_prompt_result.rendered_prompt.encode("utf-8")
        ).hexdigest()

        # 5. Metadata Processing
        source_section_types = tuple(
            sec.section_type for sec in rendered_prompt_result.rendered_sections
        )

        # Flatten and deduplicate source_item_ids preserving insertion order
        flat_item_ids = []
        for sec in rendered_prompt_result.rendered_sections:
            flat_item_ids.extend(sec.source_item_ids)
        source_item_ids = tuple(dict.fromkeys(flat_item_ids))

        # 6. Build Deterministic Constraints
        constraints = (
            SQLGenerationConstraint("target_dialect", config.target_dialect),
            SQLGenerationConstraint("require_sql_only_output", str(config.require_sql_only_output).lower()),
            SQLGenerationConstraint("allow_dml", str(config.allow_dml).lower()),
            SQLGenerationConstraint("allow_ddl", str(config.allow_ddl).lower()),
        )

        return SQLGenerationInputResult(
            raw_query=rendered_prompt_result.raw_query,
            normalized_query=rendered_prompt_result.normalized_query,
            intent_type=rendered_prompt_result.intent_type,
            target_dialect=config.target_dialect,
            rendered_prompt=rendered_prompt_result.rendered_prompt,
            prompt_sha256=prompt_sha256,
            prompt_char_count=prompt_len,
            constraints=constraints,
            source_section_types=source_section_types,
            source_item_ids=source_item_ids,
            input_version=SQL_GENERATION_INPUT_VERSION
        )
