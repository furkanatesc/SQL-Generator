import hashlib
import re
from dataclasses import dataclass
from typing import Tuple

SQL_STRUCTURED_OUTPUT_VERSION = "sql_structured_output_v1"


class SQLStructuredOutputContractError(ValueError):
    """
    Exception raised when contract invariants or validations are violated in the structured output generation layer.
    """
    pass


@dataclass(frozen=True)
class SQLStructuredOutputConfig:
    require_clean_sql: bool = True


@dataclass(frozen=True)
class SQLStructuredOutputResult:
    sql_text: str
    sql_sha256: str
    sql_char_count: int
    provider_name: str
    provider_model: str | None
    finish_reason: str
    prompt_sha256: str | None
    raw_text_sha256: str
    warnings: Tuple[str, ...]
    version: str = SQL_STRUCTURED_OUTPUT_VERSION

    def __post_init__(self) -> None:
        if self.version != SQL_STRUCTURED_OUTPUT_VERSION:
            raise SQLStructuredOutputContractError(
                f"Invalid result version: '{self.version}'. Expected '{SQL_STRUCTURED_OUTPUT_VERSION}'."
            )
        if not self.sql_text or not self.sql_text.strip():
            raise SQLStructuredOutputContractError("sql_text cannot be empty.")
        if not self.provider_name or not self.provider_name.strip():
            raise SQLStructuredOutputContractError("provider_name cannot be empty.")
        if not self.finish_reason or not self.finish_reason.strip():
            raise SQLStructuredOutputContractError("finish_reason cannot be empty.")

        # Hash and count validations
        expected_sql_sha = hashlib.sha256(self.sql_text.encode("utf-8")).hexdigest()
        if self.sql_sha256 != expected_sql_sha:
            raise SQLStructuredOutputContractError("sql_sha256 does not match the actual SHA256 of sql_text.")
        if self.sql_char_count != len(self.sql_text):
            raise SQLStructuredOutputContractError("sql_char_count does not match the actual length of sql_text.")

        # 64-char hex format checks
        if not self.sql_sha256 or not re.match(r"^[0-9a-fA-F]{64}$", self.sql_sha256):
            raise SQLStructuredOutputContractError("sql_sha256 must be a valid 64-character SHA256 hex string.")
        if not self.raw_text_sha256 or not re.match(r"^[0-9a-fA-F]{64}$", self.raw_text_sha256):
            raise SQLStructuredOutputContractError("raw_text_sha256 must be a valid 64-character SHA256 hex string.")
        if self.prompt_sha256 is not None and not re.match(r"^[0-9a-fA-F]{64}$", self.prompt_sha256):
            raise SQLStructuredOutputContractError("prompt_sha256 must be a valid 64-character SHA256 hex string.")
        if not isinstance(self.warnings, tuple):
            raise SQLStructuredOutputContractError("warnings must be a tuple.")
