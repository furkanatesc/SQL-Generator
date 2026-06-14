import hashlib
import re
from dataclasses import dataclass
from typing import Tuple

SQL_SELF_CHECK_VERSION = "sql_self_check_v1"


class SQLSelfCheckContractError(ValueError):
    """
    Exception raised when contract invariants or validations are violated in the self-check generation layer.
    """
    pass


@dataclass(frozen=True)
class SQLSelfCheckConfig:
    include_severity: bool = True


@dataclass(frozen=True)
class SQLSelfCheckItem:
    id: str
    category: str
    severity: str
    instruction: str

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise SQLSelfCheckContractError("SQLSelfCheckItem 'id' cannot be empty.")
        if not self.category or not self.category.strip():
            raise SQLSelfCheckContractError("SQLSelfCheckItem 'category' cannot be empty.")
        if not self.severity or not self.severity.strip():
            raise SQLSelfCheckContractError("SQLSelfCheckItem 'severity' cannot be empty.")
        if not self.instruction or not self.instruction.strip():
            raise SQLSelfCheckContractError("SQLSelfCheckItem 'instruction' cannot be empty.")


@dataclass(frozen=True)
class SQLSelfCheckResult:
    target_dialect: str
    sql_sha256: str
    input_version: str
    prompt_sha256: str | None
    check_items: Tuple[SQLSelfCheckItem, ...]
    self_check_prompt: str
    self_check_prompt_sha256: str
    self_check_prompt_char_count: int
    warnings: Tuple[str, ...]
    version: str = SQL_SELF_CHECK_VERSION

    def __post_init__(self) -> None:
        if self.version != SQL_SELF_CHECK_VERSION:
            raise SQLSelfCheckContractError(
                f"Invalid self-check version: '{self.version}'. Expected '{SQL_SELF_CHECK_VERSION}'."
            )
        if not self.target_dialect or not self.target_dialect.strip():
            raise SQLSelfCheckContractError("target_dialect cannot be empty.")
        if not self.sql_sha256 or not re.match(r"^[0-9a-fA-F]{64}$", self.sql_sha256):
            raise SQLSelfCheckContractError("sql_sha256 must be a valid 64-character SHA256 hex string.")
        if not self.input_version or not self.input_version.strip():
            raise SQLSelfCheckContractError("input_version cannot be empty.")
        if self.prompt_sha256 is not None and not re.match(r"^[0-9a-fA-F]{64}$", self.prompt_sha256):
            raise SQLSelfCheckContractError("prompt_sha256 must be a valid 64-character SHA256 hex string.")
        if not self.self_check_prompt or not self.self_check_prompt.strip():
            raise SQLSelfCheckContractError("self_check_prompt cannot be empty.")
        if not self.self_check_prompt_sha256 or not re.match(r"^[0-9a-fA-F]{64}$", self.self_check_prompt_sha256):
            raise SQLSelfCheckContractError("self_check_prompt_sha256 must be a valid 64-character SHA256 hex string.")

        # Check item validations
        if not self.check_items:
            raise SQLSelfCheckContractError("check_items cannot be empty.")
        if not isinstance(self.check_items, tuple):
            raise SQLSelfCheckContractError("check_items must be a tuple.")
        for item in self.check_items:
            if not isinstance(item, SQLSelfCheckItem):
                raise SQLSelfCheckContractError("All elements of check_items must be SQLSelfCheckItem instances.")

        # Check for duplicate item IDs
        ids = [item.id for item in self.check_items]
        if len(ids) != len(set(ids)):
            duplicates = set([x for x in ids if ids.count(x) > 1])
            raise SQLSelfCheckContractError(f"Duplicate check item ID(s) found: {duplicates}")

        # Hash and char count checks
        expected_prompt_sha = hashlib.sha256(self.self_check_prompt.encode("utf-8")).hexdigest()
        if self.self_check_prompt_sha256 != expected_prompt_sha:
            raise SQLSelfCheckContractError("self_check_prompt_sha256 does not match the actual SHA256 of self_check_prompt.")
        if self.self_check_prompt_char_count != len(self.self_check_prompt):
            raise SQLSelfCheckContractError("self_check_prompt_char_count does not match the actual length of self_check_prompt.")
        if not isinstance(self.warnings, tuple):
            raise SQLSelfCheckContractError("warnings must be a tuple.")
