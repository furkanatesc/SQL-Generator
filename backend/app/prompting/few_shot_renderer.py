import hashlib
from typing import Tuple
from app.prompting.few_shot_contract import (
    SQLFewShotExample,
    SQLFewShotExampleSet,
    SQLFewShotRenderConfig,
    SQLFewShotRenderResult,
    SQLFewShotContractError,
    SQL_FEW_SHOT_VERSION
)


class SQLFewShotRenderer:
    """
    Renderer class that compiles SQLFewShotExampleSet and SQLFewShotRenderConfig
    into a versioned, deterministic SQLFewShotRenderResult DTO (V1).
    """

    def render(
        self,
        example_set: SQLFewShotExampleSet,
        config: SQLFewShotRenderConfig
    ) -> SQLFewShotRenderResult:
        # 1. Input validations
        if example_set is None:
            raise SQLFewShotContractError("example_set cannot be None.")
        if config is None:
            raise SQLFewShotContractError("config cannot be None.")

        # Enforce required constraints
        if config.required and not example_set.examples:
            raise SQLFewShotContractError("Few-shot examples are required but the provided set is empty.")

        # Enforce target dialect consistency across all examples
        for ex in example_set.examples:
            if ex.dialect != config.target_dialect:
                raise SQLFewShotContractError(
                    f"Example dialect '{ex.dialect}' (ID: '{ex.id}') does not match config.target_dialect '{config.target_dialect}'."
                )

        # 2. Filter & Slice Examples
        used_examples = example_set.examples
        if config.max_examples is not None and config.max_examples < len(used_examples):
            used_examples = used_examples[:config.max_examples]

        # 3. Deterministic Formatting
        rendered_examples_text = []
        for ex in used_examples:
            ex_lines = [
                f"Example ID: {ex.id}",
                f"Question: {ex.question}"
            ]
            if ex.schema_context:
                ex_lines.append("Schema Context:")
                ex_lines.extend(f"- {item}" for item in ex.schema_context)
            
            ex_lines.append(f"SQL: {ex.sql}")
            
            if config.require_notes and ex.notes:
                ex_lines.append("Notes:")
                ex_lines.extend(f"- {note}" for note in ex.notes)
                
            rendered_examples_text.append("\n".join(ex_lines))

        rendered_text = "\n\n".join(rendered_examples_text)
        rendered_char_count = len(rendered_text)
        rendered_sha256 = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest()

        # 4. Extract example ids
        example_ids = tuple(ex.id for ex in used_examples)

        # 5. Extract and order-preserving deduplicate tags
        seen_tags = set()
        deduped_tags = []
        for ex in used_examples:
            for tag in ex.tags:
                if tag not in seen_tags:
                    seen_tags.add(tag)
                    deduped_tags.append(tag)
        tags = tuple(deduped_tags)

        return SQLFewShotRenderResult(
            dialect=config.target_dialect,
            examples=used_examples,
            rendered_text=rendered_text,
            rendered_sha256=rendered_sha256,
            rendered_char_count=rendered_char_count,
            example_ids=example_ids,
            tags=tags,
            version=SQL_FEW_SHOT_VERSION
        )
