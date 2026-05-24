import pytest
from app.eval.profiles import EvalProfile, parse_eval_profile, EvalProfileNotImplementedError
from app.eval.dataset_resolver import get_cases_for_profile

def test_parse_eval_profile_accepts_smoke():
    profile = parse_eval_profile("smoke")
    assert profile == EvalProfile.SMOKE

def test_parse_eval_profile_accepts_golden():
    profile = parse_eval_profile("golden")
    assert profile == EvalProfile.GOLDEN

def test_parse_eval_profile_rejects_invalid_profile():
    with pytest.raises(ValueError, match="Invalid eval profile 'prod'. Valid profiles: smoke, golden, large_schema"):
        parse_eval_profile("prod")

def test_default_eval_profile_is_smoke():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    assert len(cases) > 0

def test_smoke_profile_returns_few_cases():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    assert len(cases) == 1

def test_golden_profile_returns_full_dataset():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    assert len(cases) > 1

def test_large_schema_profile_is_reserved_not_default():
    with pytest.raises(EvalProfileNotImplementedError, match="large_schema profile is reserved"):
        get_cases_for_profile(EvalProfile.LARGE_SCHEMA)
