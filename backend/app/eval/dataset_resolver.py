from typing import List
from app.eval.models import GoldenCase
from app.eval.profiles import EvalProfile, EvalProfileNotImplementedError
from app.eval.golden_cases import GOLDEN_CASES

SMOKE_CASES = [
    GoldenCase(
        case_id="smoke_list_customers",
        natural_query="List all customers",
        expected_tables=["CUSTOMERS"],
        required_sql_fragments=["SELECT", "FROM"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    )
]

def get_cases_for_profile(profile: EvalProfile) -> List[GoldenCase]:
    if profile == EvalProfile.SMOKE:
        return list(SMOKE_CASES)
    elif profile == EvalProfile.GOLDEN:
        return sorted(GOLDEN_CASES, key=lambda c: c.case_id)
    elif profile == EvalProfile.LARGE_SCHEMA:
        raise EvalProfileNotImplementedError("large_schema profile is reserved for future PRs and is not implemented yet.")
    else:
        raise ValueError(f"Unknown profile: {profile}")
