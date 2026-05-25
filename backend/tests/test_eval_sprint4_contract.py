import json

import pytest

from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.fake_pipeline import DeterministicFakePipeline
from app.eval.profiles import (
    EvalProfile,
    EvalProfileNotImplementedError,
)
from app.eval.run_eval import main
from app.eval.runner import EvaluationRunner


def test_sprint4_eval_profiles_are_locked():
    assert {profile.value for profile in EvalProfile} == {
        "smoke",
        "golden",
        "large_schema",
    }


def test_sprint4_smoke_profile_contract():
    cases = get_cases_for_profile(EvalProfile.SMOKE)

    assert len(cases) == 1
    assert cases[0].case_id == "smoke_list_customers"


def test_sprint4_large_schema_profile_is_reserved():
    with pytest.raises(EvalProfileNotImplementedError):
        get_cases_for_profile(EvalProfile.LARGE_SCHEMA)


def test_sprint4_cli_smoke_json_acceptance_contract(capsys):
    exit_code = main(["--profile", "smoke", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["profile"] == "smoke"
    assert payload["summary"]["total_cases"] == 1
    assert payload["summary"]["failed"] == 0
    assert len(payload["results"]) == 1

    result = payload["results"][0]
    assert result["case_id"] == "smoke_list_customers"
    assert "error_type" in result
    assert "error_message" in result


def test_sprint4_golden_fake_fixture_acceptance_contract():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = EvaluationRunner(lambda store: DeterministicFakePipeline(store))

    suite = runner.run_suite(cases, profile=EvalProfile.GOLDEN)

    assert suite.total_cases == len(cases)
    assert suite.failed == 0


def test_sprint4_cli_exit_code_contract(capsys):
    assert main(["--profile", "smoke"]) == 0
    assert main(["--profile", "golden"]) == 0

    assert main(["--profile", "large_schema"]) == 2
    captured = capsys.readouterr()
    assert "large_schema profile is reserved" in captured.err

    assert main(["--profile", "prod"]) == 2
    captured = capsys.readouterr()
    assert "Invalid eval profile 'prod'" in captured.err
