import argparse
import json
from app.eval.golden_cases import GOLDEN_CASES
from app.eval.runner import EvaluationRunner
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
    results = runner.run_all(GOLDEN_CASES)

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count

    if args.json:
        output = {
            "summary": {
                "total_cases": len(results),
                "passed": passed_count,
                "failed": failed_count,
            },
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in r.checks],
                    "generated_sql": r.generated_sql,
                    "error_type": r.error_type
                } for r in results
            ]
        }
        print(json.dumps(output, indent=2))
        return

    print("Evaluation Summary")
    print("-" * 18)
    print(f"Total cases: {len(results)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print()

    for r in results:
        status = "[PASS]" if r.passed else "[FAIL]"
        print(f"{status} {r.case_id}")
        for c in r.checks:
            if c.passed:
                print(f"  PASS {c.name}")
            else:
                print(f"  FAIL {c.name}: {c.message}")
        print()

if __name__ == "__main__":
    main()
