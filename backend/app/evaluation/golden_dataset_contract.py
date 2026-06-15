from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

SQL_GOLDEN_DATASET_VERSION = "sql_golden_dataset_v2"


class SQLGoldenDatasetContractError(ValueError):
    """Raised when any constraint in the Golden Dataset contract is violated."""
    pass


class SQLGoldenDatasetTier(str, Enum):
    P0_CANARY = "p0_canary"
    CORE_REGRESSION = "core_regression"
    ADJUDICATION = "adjudication"


class SQLResultComparePolicy(str, Enum):
    EXACT_UNORDERED = "exact_unordered"
    EXACT_ORDERED = "exact_ordered"
    NUMERIC_TOLERANCE = "numeric_tolerance"
    SUBSET_ALLOWED = "subset_allowed"
    CUSTOM = "custom"


class SQLAdjudicationStatus(str, Enum):
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    AMBIGUOUS = "ambiguous"
    BAD_GOLD = "bad_gold"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class SQLGoldenDatasetConfig:
    version: str = SQL_GOLDEN_DATASET_VERSION
    supported_dialects: Tuple[str, ...] = ("sqlite", "postgresql", "oracle")


def _validate_not_empty(val: Any, name: str):
    """Helper to validate that a string field is not None, empty, or whitespace-only."""
    if not val or not isinstance(val, str) or not val.strip():
        raise SQLGoldenDatasetContractError(f"{name} cannot be empty")


@dataclass(frozen=True)
class SQLGoldenDatasetCase:
    case_id: str
    question: str
    dialect: str
    schema_snapshot_id: str
    fixture_ref: str
    gold_sql: str
    
    alt_valid_sql: Tuple[str, ...] = field(default_factory=tuple)
    expected_result: Any = None
    no_expected_result_reason: Optional[str] = None
    result_compare_policy: SQLResultComparePolicy = SQLResultComparePolicy.EXACT_UNORDERED
    order_sensitive: bool = False
    tolerance_policy: Optional[Dict[str, Any]] = None
    risk_tags: Tuple[str, ...] = field(default_factory=tuple)
    operator_tags: Tuple[str, ...] = field(default_factory=tuple)
    pii_tags: Tuple[str, ...] = field(default_factory=tuple)
    cost_budget: Optional[float] = None
    owner: Optional[str] = None
    adjudication_status: SQLAdjudicationStatus = SQLAdjudicationStatus.NEEDS_REVIEW
    introduced_in_version: str = SQL_GOLDEN_DATASET_VERSION
    last_reviewed_at: Optional[str] = None
    tier: SQLGoldenDatasetTier = SQLGoldenDatasetTier.CORE_REGRESSION

    def __post_init__(self):
        # Validate required fields are not empty
        _validate_not_empty(self.case_id, "case_id")
        _validate_not_empty(self.question, "question")
        _validate_not_empty(self.schema_snapshot_id, "schema_snapshot_id")
        _validate_not_empty(self.fixture_ref, "fixture_ref")
        _validate_not_empty(self.gold_sql, "gold_sql")

        # Validate dialect is supported according to config
        config = SQLGoldenDatasetConfig()
        if self.dialect not in config.supported_dialects:
            raise SQLGoldenDatasetContractError(
                f"Unsupported dialect '{self.dialect}'. Supported dialects: {sorted(config.supported_dialects)}"
            )

        # Validate and coerce enums
        try:
            object.__setattr__(self, "result_compare_policy", SQLResultComparePolicy(self.result_compare_policy))
        except ValueError:
            raise SQLGoldenDatasetContractError(f"Invalid result_compare_policy: {self.result_compare_policy}")

        try:
            object.__setattr__(self, "adjudication_status", SQLAdjudicationStatus(self.adjudication_status))
        except ValueError:
            raise SQLGoldenDatasetContractError(f"Invalid adjudication_status: {self.adjudication_status}")

        try:
            object.__setattr__(self, "tier", SQLGoldenDatasetTier(self.tier))
        except ValueError:
            raise SQLGoldenDatasetContractError(f"Invalid tier: {self.tier}")

        # P0 canary requires owner
        if self.tier == SQLGoldenDatasetTier.P0_CANARY:
            if not self.owner or not isinstance(self.owner, str) or not self.owner.strip():
                raise SQLGoldenDatasetContractError("P0 canary case requires an owner")

        # Approved case requires expected_result or reason
        if self.adjudication_status == SQLAdjudicationStatus.APPROVED:
            if self.expected_result is None and (not self.no_expected_result_reason or not isinstance(self.no_expected_result_reason, str) or not self.no_expected_result_reason.strip()):
                raise SQLGoldenDatasetContractError(
                    "Approved case must have expected_result or a non-empty no_expected_result_reason"
                )

        # Normalize and strictly check collections
        self._normalize_collection("alt_valid_sql", allow_single_str=False)
        self._normalize_collection("risk_tags", allow_single_str=True)
        self._normalize_collection("operator_tags", allow_single_str=True)
        self._normalize_collection("pii_tags", allow_single_str=True)

    def _normalize_collection(self, field_name: str, allow_single_str: bool = False):
        val = getattr(self, field_name)
        if val is None:
            normalized = ()
        elif isinstance(val, str):
            if not allow_single_str:
                raise SQLGoldenDatasetContractError(
                    f"{field_name} must be a collection of strings, not a single string"
                )
            if not val.strip():
                raise SQLGoldenDatasetContractError(f"Empty or whitespace string is not allowed in {field_name}")
            normalized = (val,)
        elif isinstance(val, (list, tuple, set)):
            # Verify all items are non-empty strings and not booleans
            for item in val:
                if not isinstance(item, str) or isinstance(item, bool):
                    raise SQLGoldenDatasetContractError(
                        f"All items in {field_name} must be strings, found type {type(item).__name__}"
                    )
                if not item.strip():
                    raise SQLGoldenDatasetContractError(f"Empty or whitespace string is not allowed in {field_name}")
            normalized = tuple(sorted(val))
        else:
            raise SQLGoldenDatasetContractError(f"{field_name} must be a collection of strings")
        
        object.__setattr__(self, field_name, normalized)


@dataclass(frozen=True)
class SQLGoldenDatasetManifest:
    cases: Tuple[SQLGoldenDatasetCase, ...] = field(default_factory=tuple)
    version: str = SQL_GOLDEN_DATASET_VERSION

    def __post_init__(self):
        if self.version != SQL_GOLDEN_DATASET_VERSION:
            raise SQLGoldenDatasetContractError(
                f"Invalid manifest version '{self.version}'. Expected '{SQL_GOLDEN_DATASET_VERSION}'"
            )

        seen_ids = set()
        for case in self.cases:
            if not isinstance(case, SQLGoldenDatasetCase):
                raise SQLGoldenDatasetContractError("Manifest cases must be instances of SQLGoldenDatasetCase")
            if case.case_id in seen_ids:
                raise SQLGoldenDatasetContractError(f"Duplicate case ID found: '{case.case_id}'")
            seen_ids.add(case.case_id)

        # Deterministically sort cases by case_id
        sorted_cases = tuple(sorted(self.cases, key=lambda c: c.case_id))
        object.__setattr__(self, "cases", sorted_cases)
