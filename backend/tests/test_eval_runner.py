from app.eval.runner import EvaluationRunner
from app.eval.models import GoldenCase
from app.trace.models import NL2SQLTrace
from app.eval.trace_recorder import RecordingTraceStore

class FakePipeline:
    def __init__(self, store: RecordingTraceStore, trace_to_save: NL2SQLTrace, should_crash: bool = False):
        self.store = store
        self.trace_to_save = trace_to_save
        self.should_crash = should_crash

    def run_pipeline(self, *, natural_query: str, **kwargs):
        if self.should_crash:
            raise RuntimeError("Pipeline crashed completely")
        self.store.save(self.trace_to_save)
        return {"success": self.trace_to_save.sql_valid is True}

def test_runner_calls_pipeline_with_natural_query():
    trace = NL2SQLTrace(sql_valid=True, selected_tables=["USERS"], generated_sql="SELECT * FROM users")

    class StrictFakePipeline:
        def __init__(self, store):
            self.store = store
            self.received_natural_query = None

        def run_pipeline(self, *, natural_query, **kwargs):
            self.received_natural_query = natural_query
            self.store.save(trace)

    holder = {}

    def factory(store):
        holder["pipeline"] = StrictFakePipeline(store)
        return holder["pipeline"]

    runner = EvaluationRunner(factory)
    case = GoldenCase(case_id="c1", natural_query="list users")

    runner.run_case(case)

    assert holder["pipeline"].received_natural_query == "list users"


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
def test_runner_applies_required_sql_features_check():
    trace = NL2SQLTrace(
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT * FROM users JOIN orders ON users.id = orders.user_id"
    )
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    case = GoldenCase(
        case_id="feature_check",
        natural_query="test",
        required_sql_features=["join"]
    )
    
    result = runner.run_case(case)
    assert result.passed is True

def test_runner_fails_case_when_required_sql_feature_missing():
    trace = NL2SQLTrace(
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT * FROM users"
    )
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    case = GoldenCase(
        case_id="feature_check_fail",
        natural_query="test",
        required_sql_features=["join"]
    )
    
    result = runner.run_case(case)
    assert result.passed is False
    
    failed_checks = [c for c in result.checks if not c.passed]
    assert len(failed_checks) == 1
    assert failed_checks[0].name == "required_sql_features"

def test_run_suite_returns_summary_counts():
    trace1 = NL2SQLTrace(sql_valid=True, selected_tables=["USERS"])
    trace2 = NL2SQLTrace(sql_valid=False) # Will fail sql_valid check

    count = [0]
    class TwoCasePipeline:
        def __init__(self, store):
            self.store = store
            
        def run_pipeline(self, *, natural_query, **kwargs):
            if count[0] == 0:
                self.store.save(trace1)
            else:
                self.store.save(trace2)
            count[0] += 1
            
    runner = EvaluationRunner(pipeline_factory=lambda store: TwoCasePipeline(store))
    cases = [
        GoldenCase(case_id="c1", natural_query="q1"),
        GoldenCase(case_id="c2", natural_query="q2")
    ]
    
    suite_result = runner.run_suite(cases)
    assert suite_result.profile == "smoke"
    assert suite_result.total_cases == 2
    assert suite_result.passed == 1
    assert suite_result.failed == 1
    assert len(suite_result.results) == 2

def test_run_suite_computes_pass_rate():
    trace = NL2SQLTrace(sql_valid=True)
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    cases = [
        GoldenCase(case_id="c1", natural_query="q1"),
        GoldenCase(case_id="c2", natural_query="q2"),
        GoldenCase(case_id="c3", natural_query="q3"),
        GoldenCase(case_id="c4", natural_query="q4")
    ]
    # all pass
    suite_result = runner.run_suite(cases)
    assert suite_result.pass_rate == 1.0

def test_suite_result_pass_rate_is_zero_when_no_cases():
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, NL2SQLTrace()))
    suite_result = runner.run_suite([])
    assert suite_result.profile == "smoke"
    assert suite_result.total_cases == 0
    assert suite_result.passed == 0
    assert suite_result.failed == 0
    assert suite_result.pass_rate == 0.0
    assert suite_result.results == []

def test_run_all_backward_compatibility_is_preserved():
    trace = NL2SQLTrace(sql_valid=True)
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store, trace))
    cases = [
        GoldenCase(case_id="c1", natural_query="q1")
    ]
    results = runner.run_all(cases)
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0].case_id == "c1"
