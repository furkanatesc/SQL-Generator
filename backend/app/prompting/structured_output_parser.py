import hashlib
import re
from app.sql_generation.sql_generation_provider_contract import SQLGenerationProviderResult
from app.prompting.structured_output_contract import (
    SQLStructuredOutputConfig,
    SQLStructuredOutputResult,
    SQLStructuredOutputContractError,
    SQL_STRUCTURED_OUTPUT_VERSION
)


class SQLStructuredOutputParser:
    """
    Parser class that validates and structured raw provider output into a
    traceable and format-guarded SQLStructuredOutputResult DTO (V1).
    """

    def parse(
        self,
        provider_result: SQLGenerationProviderResult,
        config: SQLStructuredOutputConfig
    ) -> SQLStructuredOutputResult:
        # 1. Validation checks
        if provider_result is None:
            raise SQLStructuredOutputContractError("provider_result cannot be None.")
        if config is None:
            raise SQLStructuredOutputContractError("config cannot be None.")
        
        # Verify raw text is not empty or whitespace-only
        if not provider_result.response or not provider_result.response.raw_text or not provider_result.response.raw_text.strip():
            raise SQLStructuredOutputContractError("provider_result.response.raw_text cannot be empty.")

        # Fail-fast on provider finish reason policies
        ALLOWED_SUCCESS_FINISH_REASONS = {"stop", "stop_sequence"}
        if provider_result.response.finish_reason not in ALLOWED_SUCCESS_FINISH_REASONS:
            raise SQLStructuredOutputContractError(
                f"Provider generation failed with finish_reason: '{provider_result.response.finish_reason}'."
            )

        if config.require_clean_sql:
            # 2. Markdown fenced output checks (Strict rejection, no auto-strip)
            if "```" in provider_result.response.raw_text:
                raise SQLStructuredOutputContractError(
                    "Markdown code fences (e.g. ```sql) detected in raw output. Rejecting."
                )

            # 3. Prose/Explanation detection checks (lossless invariant check)
            # Strip comments first to analyze only the actual query content
            stripped_text = re.sub(r"/\*.*?\*/", "", provider_result.response.raw_text, flags=re.DOTALL)
            stripped_text = re.sub(r"--.*$", "", stripped_text, flags=re.MULTILINE)

            clean_lines = []
            for line in stripped_text.splitlines():
                line_strip = line.strip()
                if line_strip:
                    clean_lines.append(line_strip)

            if not clean_lines:
                raise SQLStructuredOutputContractError("No SQL statements found in raw output.")

            # First clean line must start with a valid SQL keyword
            first_line_lower = clean_lines[0].lower()
            sql_start_keywords = {"select", "with", "insert", "update", "delete", "create", "drop", "alter"}
            
            first_word_match = re.findall(r"\b[a-z_]+\b", first_line_lower)
            if not first_word_match or first_word_match[0] not in sql_start_keywords:
                raise SQLStructuredOutputContractError(
                    "Prose/explanation detected at the beginning of raw output. Rejecting."
                )

            # Reject if there is any clean line after a semicolon that contains alphabetical characters (prose after SQL)
            has_semicolon = False
            for line in clean_lines:
                if has_semicolon:
                    if re.search(r"[a-zA-Z]", line):
                        raise SQLStructuredOutputContractError(
                            f"Prose/explanation text detected after SQL statement: '{line}'. Rejecting."
                        )
                if ";" in line:
                    has_semicolon = True

            # Heuristic checks for prose/explanation lines
            prose_keywords = {"this", "query", "returns", "selects", "shows", "explanation", "note", "here", "is", "the", "to", "for", "we", "can", "use", "get", "fetch", "result", "results", "table", "column", "row", "rows"}
            for line in clean_lines:
                # 1. Line ending with period and containing no SQL symbols/operators
                if line.endswith(".") and not any(c in line for c in (";", "=", "<", ">", ",", "(", ")", "*", "'", '"')):
                    raise SQLStructuredOutputContractError(
                        f"Prose/explanation text detected in raw output line: '{line}'. Rejecting."
                    )
                # 2. Line that looks like natural language (contains prose keywords, no SQL keywords or symbols)
                line_lower = line.lower()
                clean_line_words = re.sub(r"[.:\(\)]", " ", line_lower)
                words = [w for w in clean_line_words.split() if w.isalpha()]
                if words:
                    # Known label check
                    if len(words) == 1 and words[0] in {"explanation", "note", "notes", "warning", "info", "comment", "comments", "output", "sql"}:
                        raise SQLStructuredOutputContractError(
                            f"Prose/explanation label detected in raw output: '{line}'. Rejecting."
                        )
                    # Sentence check: 2 or more words, has prose keywords, no SQL symbols or SQL keywords
                    if len(words) >= 2:
                        sql_symbols = {";", "=", "<", ">", ",", "(", ")", "*", "'", '"', "+", "/"}
                        sql_keywords = {
                            "select", "from", "where", "join", "on", "group", "order", "limit",
                            "having", "and", "or", "in", "like", "not", "null", "as", "into",
                            "values", "set", "union", "all", "exists", "between", "case", "when",
                            "then", "else", "end", "is", "by", "create", "table", "insert", "update", "delete"
                        }
                        if not any(sym in line for sym in sql_symbols) and not any(w in sql_keywords for w in words):
                            if any(w in prose_keywords for w in words):
                                raise SQLStructuredOutputContractError(
                                    f"Prose/explanation text detected in raw output line: '{line}'. Rejecting."
                                )

        # 4. Compile Structured Output Result DTO
        sql_text = provider_result.response.raw_text
        sql_char_count = len(sql_text)
        sql_sha256 = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
        
        raw_text_sha256 = hashlib.sha256(provider_result.response.raw_text.encode("utf-8")).hexdigest()

        return SQLStructuredOutputResult(
            sql_text=sql_text,
            sql_sha256=sql_sha256,
            sql_char_count=sql_char_count,
            provider_name=provider_result.response.provider_id,
            provider_model=provider_result.response.model_id,
            finish_reason=provider_result.response.finish_reason,
            prompt_sha256=provider_result.prompt_sha256,
            raw_text_sha256=raw_text_sha256,
            warnings=(),
            version=SQL_STRUCTURED_OUTPUT_VERSION
        )
