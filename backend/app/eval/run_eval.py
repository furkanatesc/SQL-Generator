import argparse
import json
from app.eval.golden_cases import GOLDEN_CASES
from app.eval.runner import EvaluationRunner
from app.trace.store import RecordingTraceStore

# Dummy pipeline to make the CLI runnable if real pipeline isn't hooked up yet, 
# or we can import the real pipeline if it exists. 
# For now, to keep it simple and independent, we'll try to import the real one
# and fall back to a mock if needed, but the instructions say "bu PR'da test 
# düzeyinde çalışacak". Let's provide a basic hook for the real pipeline.
try:
    from app.sql_pipeline import SQLPipeline
    from app.llm_client import LLMClient
    from app.schema_manager import SchemaManager
    from app.nlp.embeddings import EmbeddingModel
    def get_real_pipeline(store: RecordingTraceStore):
        # We need to initialize the real pipeline.
        # However, to avoid real LLM calls by mistake in eval right now,
        # and since this is just an evaluation skeleton, let's use a fake pipeline
        # in the CLI by default unless configured otherwise.
        # Actually, the user says "python -m app.eval.run_eval" should work.
        pass
except ImportError:
    pass

class FakePipelineForCLI:
    def __init__(self, store: RecordingTraceStore):
        self.store = store
        
    def run_pipeline(self, query: str):
        from app.trace.models import NL2SQLTrace
        trace = NL2SQLTrace(
            raw_query=query,
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
