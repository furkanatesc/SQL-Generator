import argparse
import json
from app.eval.golden_cases import GOLDEN_CASES
from app.eval.runner import EvaluationRunner
from app.eval.reporting import suite_result_to_dict
from app.eval.trace_recorder import RecordingTraceStore

class FakePipelineForCLI:
    def __init__(self, store: RecordingTraceStore):
        self.store = store
        
    def run_pipeline(self, *, natural_query: str, **kwargs):
        from app.trace.models import NL2SQLTrace
        trace = NL2SQLTrace(
            raw_query=natural_query,
            sql_valid=True,
            selected_tables=["CUSTOMERS"],
            generated_sql="SELECT * FROM customers"
        )
        self.store.save(trace)

def main():
    parser = argparse.ArgumentParser(description="Run NL2SQL Evaluation")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    # In PR 4.1, we use a fake pipeline so we don't hit the real LLM API.
    # The user explicitly said: "Eval testleri veya default runner gerçek LLM çağırırsa PR reddedilir."
    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipelineForCLI(store))
    suite_result = runner.run_suite(GOLDEN_CASES)

    if args.json:
        output = suite_result_to_dict(suite_result)
        print(json.dumps(output, indent=2))
        return

    print("Evaluation Summary")
    print("-" * 18)
    print(f"Total cases: {suite_result.total_cases}")
    print(f"Passed: {suite_result.passed}")
    print(f"Failed: {suite_result.failed}")
    print(f"Pass rate: {suite_result.pass_rate * 100:.2f}%")
    print()

    for r in suite_result.results:
        status = "[PASS]" if r.passed else "[FAIL]"
        print(f"{status} {r.case_id}")
        for c in r.checks:
            if c.passed:
                print(f"  PASS {c.name}")
            else:
                msg = c.message if c.message else "Failed"
                print(f"  FAIL {c.name}: {msg}")
        print()

if __name__ == "__main__":
    main()
