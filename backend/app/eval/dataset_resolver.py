from typing import List
from app.eval.models import GoldenCase
from app.eval.profiles import EvalProfile, EvalProfileNotImplementedError
from app.eval.golden_cases import GOLDEN_CASES

SMOKE_CASES = [
    GOLDEN_CASES[0]
]

def get_cases_for_profile(profile: EvalProfile) -> List[GoldenCase]:
    if profile == EvalProfile.SMOKE:
        return SMOKE_CASES
    elif profile == EvalProfile.GOLDEN:
        return GOLDEN_CASES
    elif profile == EvalProfile.LARGE_SCHEMA:
        raise EvalProfileNotImplementedError("large_schema profile is reserved for future PRs and is not implemented yet.")
    else:
        raise ValueError(f"Unknown profile: {profile}")
