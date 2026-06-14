import hashlib
from app.prompting.structured_output_contract import SQLStructuredOutputResult
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.prompting.self_check_contract import (
    SQLSelfCheckConfig,
    SQLSelfCheckItem,
    SQLSelfCheckResult,
    SQLSelfCheckContractError,
    SQL_SELF_CHECK_VERSION,
)


class SQLSelfCheckGenerator:
    """
    Generator class that creates a deterministic self-check checklist and prompt
    for a given structured SQL output and query input.
    """

    def generate(
        self,
        structured_output: SQLStructuredOutputResult,
        generation_input: SQLGenerationInputResult,
        config: SQLSelfCheckConfig
    ) -> SQLSelfCheckResult:
        # 1. Validation checks
        if structured_output is None:
            raise SQLSelfCheckContractError("structured_output cannot be None.")
        if generation_input is None:
            raise SQLSelfCheckContractError("generation_input cannot be None.")
        if config is None:
            raise SQLSelfCheckContractError("config cannot be None.")

        # Verify SQL sha256 integrity match
        computed_sql_sha = hashlib.sha256(structured_output.sql_text.encode("utf-8")).hexdigest()
        if structured_output.sql_sha256 != computed_sql_sha:
            raise SQLSelfCheckContractError("structured_output.sql_sha256 mismatch against computed hash.")

        if not generation_input.target_dialect or not generation_input.target_dialect.strip():
            raise SQLSelfCheckContractError("generation_input.target_dialect cannot be empty.")

        # 2. Compile deterministic SQLSelfCheckItem checklist
        check_items = (
            SQLSelfCheckItem(
                id="chk_intent_alignment",
                category="intent_alignment",
                severity="high",
                instruction="Does the SQL answer the user intent?"
            ),
            SQLSelfCheckItem(
                id="chk_schema_alignment_tables",
                category="schema_alignment",
                severity="high",
                instruction="Does the SQL only use selected / allowed tables?"
            ),
            SQLSelfCheckItem(
                id="chk_schema_alignment_columns",
                category="schema_alignment",
                severity="high",
                instruction="Does the SQL avoid hallucinated columns?"
            ),
            SQLSelfCheckItem(
                id="chk_relationship_alignment",
                category="relationship_alignment",
                severity="high",
                instruction="Are joins consistent with selected relationships / join paths?"
            ),
            SQLSelfCheckItem(
                id="chk_dialect_safety",
                category="dialect_safety",
                severity="high",
                instruction="Is the SQL compatible with the target dialect?"
            ),
            SQLSelfCheckItem(
                id="chk_safety_guardrail",
                category="safety_guardrail",
                severity="critical",
                instruction="Does the SQL avoid destructive or unsafe statements unless explicitly allowed?"
            ),
            SQLSelfCheckItem(
                id="chk_output_shape",
                category="output_shape",
                severity="medium",
                instruction="Does the SQL output only SQL-relevant result columns?"
            )
        )

        # 3. Build deterministic self_check_prompt
        self_check_prompt = (
            "You are a SQL self-check validator.\n"
            "Your task is to analyze the generated SQL and answer the self-check checklist questions.\n\n"
            f"Target Dialect: {generation_input.target_dialect}\n"
            f"User Query: {generation_input.raw_query}\n\n"
            "Generated SQL:\n"
            "```\n"
            f"{structured_output.sql_text}\n"
            "```\n\n"
            "Self-Check Checklist:\n"
        )
        for item in check_items:
            severity_str = f" [{item.severity.upper()}]" if config.include_severity else ""
            self_check_prompt += f"- [ ] {item.instruction} (Category: {item.category}{severity_str})\n"

        # 4. Compute metrics and hashes
        self_check_prompt_sha256 = hashlib.sha256(self_check_prompt.encode("utf-8")).hexdigest()
        self_check_prompt_char_count = len(self_check_prompt)

        return SQLSelfCheckResult(
            target_dialect=generation_input.target_dialect,
            sql_sha256=structured_output.sql_sha256,
            input_version=generation_input.input_version,
            prompt_sha256=generation_input.prompt_sha256,
            check_items=check_items,
            self_check_prompt=self_check_prompt,
            self_check_prompt_sha256=self_check_prompt_sha256,
            self_check_prompt_char_count=self_check_prompt_char_count,
            warnings=(),
            version=SQL_SELF_CHECK_VERSION
        )
