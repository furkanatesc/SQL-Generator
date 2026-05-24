import pytest
from app.eval.profiles import EvalProfile, parse_eval_profile, EvalProfileNotImplementedError
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.run_eval import build_parser

def test_parse_eval_profile_accepts_smoke():
    profile = parse_eval_profile("smoke")
    assert profile == EvalProfile.SMOKE

def test_parse_eval_profile_accepts_golden():
    profile = parse_eval_profile("golden")
    assert profile == EvalProfile.GOLDEN

def test_parse_eval_profile_rejects_invalid_profile():
    with pytest.raises(ValueError, match="Invalid eval profile 'prod'. Valid profiles: smoke, golden, large_schema"):
        parse_eval_profile("prod")

def test_smoke_profile_returns_cases():
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

def test_eval_cli_defaults_to_smoke_profile():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.profile == "smoke"

def test_eval_cli_accepts_golden_profile():
    parser = build_parser()
    args = parser.parse_args(["--profile", "golden"])
    assert args.profile == "golden"
