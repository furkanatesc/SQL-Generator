import pytest
from app.eval.fake_pipeline import DeterministicFakePipeline, FAKE_SQL_BY_CASE_ID, FAKE_SELECTED_TABLES_BY_CASE_ID
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.profiles import EvalProfile
from app.eval.runner import EvaluationRunner

def test_every_smoke_case_has_deterministic_fake_sql():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    missing_sql = [
        case.case_id
        for case in cases
        if case.case_id not in FAKE_SQL_BY_CASE_ID
    ]
    missing_tables = [
        case.case_id
        for case in cases
        if case.case_id not in FAKE_SELECTED_TABLES_BY_CASE_ID
    ]
    assert missing_sql == []
    assert missing_tables == []

def test_every_golden_case_has_deterministic_fake_sql():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    missing_sql = [
        case.case_id
        for case in cases
        if case.case_id not in FAKE_SQL_BY_CASE_ID
    ]
    missing_tables = [
        case.case_id
        for case in cases
        if case.case_id not in FAKE_SELECTED_TABLES_BY_CASE_ID
    ]
    assert missing_sql == []
    assert missing_tables == []

def test_fake_pipeline_fails_fast_for_unknown_case_id():
    class DummyStore:
        def save(self, trace): pass
        
    pipeline = DeterministicFakePipeline(DummyStore())
    
    with pytest.raises(KeyError, match="No deterministic fake SQL configured"):
        pipeline.run_pipeline(
            job_id="eval:unknown_case",
            natural_query="unknown"
        )

def test_deterministic_fake_sql_fixture_satisfies_golden_case_expectations():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = EvaluationRunner(lambda store: DeterministicFakePipeline(store))

    suite = runner.run_suite(cases, profile=EvalProfile.GOLDEN)

    assert suite.total_cases == len(cases)
    assert suite.failed == 0

def test_deterministic_fake_sql_fixture_satisfies_smoke_case_expectations():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    runner = EvaluationRunner(lambda store: DeterministicFakePipeline(store))

    suite = runner.run_suite(cases, profile=EvalProfile.SMOKE)

    assert suite.total_cases == 1
    assert suite.failed == 0
