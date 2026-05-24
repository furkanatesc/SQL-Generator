from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    natural_query: str

    expected_tables: List[str] = field(default_factory=list)
    expected_columns: List[str] = field(default_factory=list)

    required_sql_fragments: List[str] = field(default_factory=list)
    forbidden_sql_fragments: List[str] = field(default_factory=list)

    required_sql_features: List[str] = field(default_factory=list)
    forbidden_sql_features: List[str] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCheckResult:
    name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    passed: bool
    checks: List[EvalCheckResult]
    generated_sql: Optional[str] = None
    error_type: Optional[str] = None


@dataclass(frozen=True)
class EvalSuiteResult:
    profile: str
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    results: List[EvalCaseResult]
