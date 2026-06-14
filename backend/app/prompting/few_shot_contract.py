import hashlib
from dataclasses import dataclass
from typing import Tuple

SQL_FEW_SHOT_VERSION = "sql_few_shot_v1"
SUPPORTED_DIALECTS = {"sqlite", "postgresql", "oracle"}


class SQLFewShotContractError(ValueError):
    """
    Exception raised when contract invariants or validations are violated in the few-shot framework.
    """
    pass


@dataclass(frozen=True)
class SQLFewShotExample:
    id: str
    dialect: str
    intent_type: str
    question: str
    schema_context: Tuple[str, ...]
    sql: str
    notes: Tuple[str, ...]
    tags: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise SQLFewShotContractError("Example 'id' cannot be empty.")
        if not self.dialect or not self.dialect.strip():
            raise SQLFewShotContractError("Example 'dialect' cannot be empty.")
        if self.dialect not in SUPPORTED_DIALECTS:
            raise SQLFewShotContractError(f"Unsupported example dialect: '{self.dialect}'.")
        if not self.intent_type or not self.intent_type.strip():
            raise SQLFewShotContractError("Example 'intent_type' cannot be empty.")
        if not self.question or not self.question.strip():
            raise SQLFewShotContractError("Example 'question' cannot be empty.")
        if not self.sql or not self.sql.strip():
            raise SQLFewShotContractError("Example 'sql' cannot be empty.")
        if not isinstance(self.schema_context, tuple):
            raise SQLFewShotContractError("Example 'schema_context' must be a tuple.")
        if not isinstance(self.notes, tuple):
            raise SQLFewShotContractError("Example 'notes' must be a tuple.")
        if not isinstance(self.tags, tuple):
            raise SQLFewShotContractError("Example 'tags' must be a tuple.")


@dataclass(frozen=True)
class SQLFewShotExampleSet:
    examples: Tuple[SQLFewShotExample, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.examples, tuple):
            raise SQLFewShotContractError("'examples' must be a tuple of SQLFewShotExample.")
        
        seen_ids = set()
        for ex in self.examples:
            if not isinstance(ex, SQLFewShotExample):
                raise SQLFewShotContractError("All examples must be of type SQLFewShotExample.")
            if ex.id in seen_ids:
                raise SQLFewShotContractError(f"Duplicate example ID found in set: '{ex.id}'.")
            seen_ids.add(ex.id)


@dataclass(frozen=True)
class SQLFewShotRenderConfig:
    target_dialect: str
    require_notes: bool = True
    max_examples: int | None = None
    required: bool = True

    def __post_init__(self) -> None:
        if not self.target_dialect or self.target_dialect not in SUPPORTED_DIALECTS:
            raise SQLFewShotContractError(f"Unsupported target dialect: '{self.target_dialect}'.")
        if self.max_examples is not None and self.max_examples <= 0:
            raise SQLFewShotContractError("max_examples must be a positive integer if defined.")


@dataclass(frozen=True)
class SQLFewShotRenderResult:
    dialect: str
    examples: Tuple[SQLFewShotExample, ...]
    rendered_text: str
    rendered_sha256: str
    rendered_char_count: int
    example_ids: Tuple[str, ...]
    tags: Tuple[str, ...]
    version: str = SQL_FEW_SHOT_VERSION

    def __post_init__(self) -> None:
        if self.version != SQL_FEW_SHOT_VERSION:
            raise SQLFewShotContractError(
                f"Invalid result version: '{self.version}'. Expected '{SQL_FEW_SHOT_VERSION}'."
            )
        if not self.dialect or self.dialect not in SUPPORTED_DIALECTS:
            raise SQLFewShotContractError(f"Unsupported dialect: '{self.dialect}'.")
        if not isinstance(self.examples, tuple):
            raise SQLFewShotContractError("'examples' must be a tuple.")
        
        # Verify rendered text matches metadata values
        expected_sha = hashlib.sha256(self.rendered_text.encode("utf-8")).hexdigest()
        if self.rendered_sha256 != expected_sha:
            raise SQLFewShotContractError("rendered_sha256 does not match the actual SHA256 of rendered_text.")
        if self.rendered_char_count != len(self.rendered_text):
            raise SQLFewShotContractError("rendered_char_count does not match the actual length of rendered_text.")
            
        # Verify example IDs order matches examples tuple
        expected_ids = tuple(ex.id for ex in self.examples)
        if self.example_ids != expected_ids:
            raise SQLFewShotContractError("example_ids must match the ordered IDs of the provided examples.")
