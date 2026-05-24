from typing import List, Callable, Any
from app.eval.models import GoldenCase, EvalCaseResult, EvalCheckResult
from app.eval.checks import (
    check_sql_valid,
    check_expected_tables,
    check_required_sql_fragments,
    check_forbidden_sql_fragments,
    check_required_sql_features,
    check_forbidden_sql_features
)
from app.eval.trace_recorder import RecordingTraceStore

class EvaluationRunner:
    def __init__(self, pipeline_factory: Callable[[RecordingTraceStore], Any]):
        """
        pipeline_factory should be a callable that takes a RecordingTraceStore
        and returns an instance of a pipeline. This allows the runner to
        inject a recording store to capture the trace for each run.
        """
        self.pipeline_factory = pipeline_factory

    def run_case(self, case: GoldenCase) -> EvalCaseResult:
        store = RecordingTraceStore()
        pipeline = self.pipeline_factory(store)
        
        try:
            # We assume the pipeline takes natural_query as input
            pipeline.run_pipeline(
                job_id=f"eval:{case.case_id}",
                natural_query=case.natural_query
            )
        except Exception as e:
            # We don't want the suite to crash if one case fails badly
            pass
        
        # At this point, the pipeline should have saved a trace.
        # If it didn't (e.g. crashed before saving), we handle it.
        if not store.saved:
            return EvalCaseResult(
                case_id=case.case_id,
                passed=False,
                checks=[],
                error_type="MissingTraceError"
            )
            
        trace = store.saved[0]
        
        checks: List[EvalCheckResult] = []
        
        checks.append(check_sql_valid(trace))
        if case.expected_tables:
            checks.append(check_expected_tables(trace, case))
        if case.required_sql_fragments:
            checks.append(check_required_sql_fragments(trace, case))
        if case.forbidden_sql_fragments:
            checks.append(check_forbidden_sql_fragments(trace, case))
        if case.required_sql_features:
            checks.append(check_required_sql_features(trace, case))
        if case.forbidden_sql_features:
            checks.append(check_forbidden_sql_features(trace, case))
            
        passed = all(c.passed for c in checks)
        
        return EvalCaseResult(
            case_id=case.case_id,
            passed=passed,
            checks=checks,
            generated_sql=trace.generated_sql,
            error_type=trace.error_type
        )

    def run_all(self, cases: List[GoldenCase]) -> List[EvalCaseResult]:
        return [self.run_case(case) for case in cases]
