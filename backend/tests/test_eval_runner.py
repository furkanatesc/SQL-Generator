from app.eval.runner import EvaluationRunner
from app.eval.models import GoldenCase
from app.trace.models import NL2SQLTrace
from app.trace.store import RecordingTraceStore

class FakePipeline:
    def __init__(self, store: RecordingTraceStore, trace_to_save: NL2SQLTrace, should_crash: bool = False):
        self.store = store
        self.trace_to_save = trace_to_save
        self.should_crash = should_crash

    def run_pipeline(self, **kwargs):
        if self.should_crash:
            raise RuntimeError("Pipeline crashed completely")
        self.store.save(self.trace_to_save)
        return {"success": self.trace_to_save.sql_valid is True}

def test_runner_runs_single_case_and_returns_passed_result():
    trace = NL2SQLTrace(
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT * FROM users"
    )
    
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    case = GoldenCase(
        case_id="single_pass",
        natural_query="test",
        expected_tables=["USERS"],
        required_sql_fragments=["SELECT"]
    )
    
    result = runner.run_case(case)
    assert result.passed is True
    assert result.case_id == "single_pass"
    assert len(result.checks) > 0
    assert all(c.passed for c in result.checks)

def test_runner_returns_failed_result_when_required_table_missing():
    trace = NL2SQLTrace(
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT * FROM users"
    )
    
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    case = GoldenCase(
        case_id="missing_table",
        natural_query="test",
        expected_tables=["USERS", "ORDERS"]
    )
    
    result = runner.run_case(case)
    assert result.passed is False
    assert result.case_id == "missing_table"
    
    # Check that specifically the expected_tables check failed
    failed_checks = [c for c in result.checks if not c.passed]
    assert len(failed_checks) == 1
    assert failed_checks[0].name == "expected_tables"

def test_runner_runs_all_cases():
    trace = NL2SQLTrace(sql_valid=True, selected_tables=["USERS"])
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    
    cases = [
        GoldenCase(case_id="c1", natural_query="q1", expected_tables=["USERS"]),
        GoldenCase(case_id="c2", natural_query="q2", expected_tables=["ORDERS"])
    ]
    
    results = runner.run_all(cases)
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False

def test_runner_handles_pipeline_crash_gracefully():
    # It should not raise an exception, but return a failed EvalCaseResult
    trace = NL2SQLTrace() # Won't be saved
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace, should_crash=True))
    
    case = GoldenCase(case_id="crash_case", natural_query="test")
    result = runner.run_case(case)
    
    assert result.passed is False
    assert result.error_type == "MissingTraceError"
