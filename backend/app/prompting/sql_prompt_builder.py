import hashlib
from typing import Tuple
from app.sql_generation import SQLGenerationProviderContractError
from app.prompting.sql_prompt_builder_contract import (
    SQLPromptBuilderConfig,
    SQLPromptBuilderSection,
    SQLPromptBuilderResult,
    SQL_PROMPT_BUILDER_VERSION
)
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult


class SQLPromptBuilder:
    """
    Builder class that compiles SQLGenerationInputResult and SQLPromptBuilderConfig
    into a versioned, deterministic SQLPromptBuilderResult DTO (V2).
    """

    def build(
        self,
        input_result: SQLGenerationInputResult,
        config: SQLPromptBuilderConfig
    ) -> SQLPromptBuilderResult:
        # 1. Validate inputs
        if input_result is None:
            raise SQLGenerationProviderContractError("input_result cannot be None.")
        if config is None:
            raise SQLGenerationProviderContractError("config cannot be None.")
        if not input_result.rendered_prompt or not input_result.rendered_prompt.strip():
            raise SQLGenerationProviderContractError("input_result.rendered_prompt cannot be empty.")

        # 2. Parse the V1 rendered prompt
        lines = input_result.rendered_prompt.splitlines()
        parts = input_result.rendered_prompt.split("## ")
        
        parsed_sections = {}
        for part in parts:
            part = part.strip()
            if not part:
                continue
            part_lines = part.splitlines()
            title = part_lines[0].strip()
            content_items = []
            for line in part_lines[1:]:
                line_strip = line.strip()
                if line_strip.startswith("- "):
                    content_items.append(line_strip[2:].strip())
            parsed_sections[title] = tuple(content_items)

        # Validate presence of required sections
        v1_required_titles = [
            "System Instructions",
            "User Intent",
            "Schema Context",
            "Constraints",
            "Output Contract"
        ]
        for req_title in v1_required_titles:
            if req_title not in parsed_sections:
                raise SQLGenerationProviderContractError(
                    f"Required V1 section '{req_title}' is missing in the rendered prompt."
                )

        if "Relationship Context" not in parsed_sections:
            parsed_sections["Relationship Context"] = ()

        # 3. Create Dialect Rules
        rules = [
            f"The target SQL dialect is {config.target_dialect.upper() if config.target_dialect != 'sqlite' else 'SQLite'}."
        ]
        if not config.allow_dml:
            rules.append("DML (Data Manipulation Language) operations are not allowed.")
        if not config.allow_ddl:
            rules.append("DDL (Data Definition Language) operations are not allowed.")
        dialect_rules_content = tuple(rules)

        # 4. Create Output Contract
        output_items = list(parsed_sections["Output Contract"])
        sql_only_instruction = "Return only SQL. No markdown. No explanation."
        if config.require_sql_only_output:
            if sql_only_instruction not in output_items:
                output_items.append(sql_only_instruction)
        output_contract_content = tuple(output_items)

        # 5. Build V2 Sections
        # Order: system_rules > dialect_rules > schema_context > relationship_context 
        #        > user_intent > generation_constraints > output_contract
        system_rules_sec = SQLPromptBuilderSection(
            section_type="system_rules",
            title="System Rules",
            content_items=parsed_sections["System Instructions"],
            required=True
        )
        dialect_rules_sec = SQLPromptBuilderSection(
            section_type="dialect_rules",
            title="Dialect Rules",
            content_items=dialect_rules_content,
            required=True
        )
        schema_context_sec = SQLPromptBuilderSection(
            section_type="schema_context",
            title="Schema Context",
            content_items=parsed_sections["Schema Context"],
            required=True
        )
        relationship_context_sec = SQLPromptBuilderSection(
            section_type="relationship_context",
            title="Relationship Context",
            content_items=parsed_sections["Relationship Context"],
            required=False
        )
        user_intent_sec = SQLPromptBuilderSection(
            section_type="user_intent",
            title="User Intent",
            content_items=parsed_sections["User Intent"],
            required=True
        )
        generation_constraints_sec = SQLPromptBuilderSection(
            section_type="generation_constraints",
            title="Generation Constraints",
            content_items=parsed_sections["Constraints"],
            required=True
        )
        output_contract_sec = SQLPromptBuilderSection(
            section_type="output_contract",
            title="Output Contract",
            content_items=output_contract_content,
            required=True
        )

        sections_list = (
            system_rules_sec,
            dialect_rules_sec,
            schema_context_sec,
            relationship_context_sec,
            user_intent_sec,
            generation_constraints_sec,
            output_contract_sec
        )

        # 6. Format and Render
        rendered_sections_text = []
        for sec in sections_list:
            sec_lines = [f"## {sec.title}"]
            if sec.content_items:
                sec_lines.extend(f"- {item}" for item in sec.content_items)
            rendered_sections_text.append("\n".join(sec_lines))

        prompt_text = "\n\n".join(rendered_sections_text)
        prompt_char_count = len(prompt_text)

        # Fail-fast check on max prompt chars budget
        if prompt_char_count > config.max_prompt_chars:
            raise SQLGenerationProviderContractError(
                f"Prompt character count ({prompt_char_count}) exceeds "
                f"maximum configured limit ({config.max_prompt_chars})."
            )

        prompt_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

        # 7. Deduplicate source_item_ids
        seen = set()
        deduped_ids = []
        for item in input_result.source_item_ids:
            if item not in seen:
                seen.add(item)
                deduped_ids.append(item)
        source_item_ids = tuple(deduped_ids)

        return SQLPromptBuilderResult(
            target_dialect=config.target_dialect,
            prompt_text=prompt_text,
            prompt_sha256=prompt_sha256,
            prompt_char_count=prompt_char_count,
            sections=sections_list,
            section_types=tuple(sec.section_type for sec in sections_list),
            source_item_ids=source_item_ids,
            constraints=input_result.constraints,
            version=SQL_PROMPT_BUILDER_VERSION
        )
