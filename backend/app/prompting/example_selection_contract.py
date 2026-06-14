import re
from dataclasses import dataclass
from typing import Tuple
from app.prompting.few_shot_contract import SQLFewShotExample, SUPPORTED_DIALECTS

SQL_EXAMPLE_SELECTION_VERSION = "sql_example_selection_v1"


class SQLExampleSelectionContractError(ValueError):
    """
    Exception raised when contract invariants or validations are violated in the example selection layer.
    """
    pass


@dataclass(frozen=True)
class SQLExampleSelectionConfig:
    target_dialect: str
    max_examples: int = 3
    required: bool = True

    def __post_init__(self) -> None:
        if not self.target_dialect or self.target_dialect not in SUPPORTED_DIALECTS:
            raise SQLExampleSelectionContractError(f"Unsupported target dialect: '{self.target_dialect}'.")
        if self.max_examples <= 0:
            raise SQLExampleSelectionContractError("max_examples must be a positive integer.")


@dataclass(frozen=True)
class SQLExampleSelectionCandidate:
    example: SQLFewShotExample
    score: int

    def __post_init__(self) -> None:
        if not isinstance(self.example, SQLFewShotExample):
            raise SQLExampleSelectionContractError("Candidate example must be of type SQLFewShotExample.")
        if self.score < 0:
            raise SQLExampleSelectionContractError("Candidate score cannot be negative.")


@dataclass(frozen=True)
class SQLExampleSelectionReason:
    example_id: str
    score: int
    matched_signals: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.example_id or not self.example_id.strip():
            raise SQLExampleSelectionContractError("Reason 'example_id' cannot be empty.")
        if self.score < 0:
            raise SQLExampleSelectionContractError("Reason score cannot be negative.")
        if not isinstance(self.matched_signals, tuple):
            raise SQLExampleSelectionContractError("Reason 'matched_signals' must be a tuple of strings.")


@dataclass(frozen=True)
class SQLExampleSelectionResult:
    target_dialect: str
    intent_type: str
    selected_examples: Tuple[SQLFewShotExample, ...]
    selected_example_ids: Tuple[str, ...]
    rejected_example_ids: Tuple[str, ...]
    selection_reasons: Tuple[SQLExampleSelectionReason, ...]
    max_examples: int
    selection_fingerprint: str
    version: str = SQL_EXAMPLE_SELECTION_VERSION

    def __post_init__(self) -> None:
        if self.version != SQL_EXAMPLE_SELECTION_VERSION:
            raise SQLExampleSelectionContractError(
                f"Invalid result version: '{self.version}'. Expected '{SQL_EXAMPLE_SELECTION_VERSION}'."
            )
        if not self.target_dialect or self.target_dialect not in SUPPORTED_DIALECTS:
            raise SQLExampleSelectionContractError(f"Unsupported target dialect: '{self.target_dialect}'.")
        if not self.intent_type or not self.intent_type.strip():
            raise SQLExampleSelectionContractError("intent_type cannot be empty.")
        if not isinstance(self.selected_examples, tuple):
            raise SQLExampleSelectionContractError("selected_examples must be a tuple.")
        if not isinstance(self.selected_example_ids, tuple):
            raise SQLExampleSelectionContractError("selected_example_ids must be a tuple.")
        if not isinstance(self.rejected_example_ids, tuple):
            raise SQLExampleSelectionContractError("rejected_example_ids must be a tuple.")
        if not isinstance(self.selection_reasons, tuple):
            raise SQLExampleSelectionContractError("selection_reasons must be a tuple.")
        if self.max_examples <= 0:
            raise SQLExampleSelectionContractError("max_examples must be a positive integer.")
            
        # Enforce fingerprint 64-char hex format
        if not self.selection_fingerprint or not re.match(r"^[0-9a-fA-F]{64}$", self.selection_fingerprint):
            raise SQLExampleSelectionContractError("selection_fingerprint must be a valid 64-character SHA256 hex string.")

        # Verify selected_example_ids order matches selected_examples ordered IDs
        expected_ids = tuple(ex.id for ex in self.selected_examples)
        if self.selected_example_ids != expected_ids:
            raise SQLExampleSelectionContractError("selected_example_ids must match the ordered IDs of selected_examples.")

        # Verify selection reasons length matches selected_examples length
        if len(self.selection_reasons) != len(self.selected_examples):
            raise SQLExampleSelectionContractError("Length of selection_reasons must match selected_examples.")

        # Verify selection reasons example IDs match selected examples
        for idx, reason in enumerate(self.selection_reasons):
            if reason.example_id != self.selected_examples[idx].id:
                raise SQLExampleSelectionContractError(
                    f"Reason ID '{reason.example_id}' at index {idx} does not match selected example ID '{self.selected_examples[idx].id}'."
                )

        # Enforce selected examples dialect invariant
        for ex in self.selected_examples:
            if ex.dialect != self.target_dialect:
                raise SQLExampleSelectionContractError(
                    f"Selected example ID '{ex.id}' dialect '{ex.dialect}' "
                    f"does not match target_dialect '{self.target_dialect}'."
                )
