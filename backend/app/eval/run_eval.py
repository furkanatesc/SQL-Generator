import argparse
import json
import sys
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.fake_pipeline import DeterministicFakePipeline
from app.eval.models import EvalSuiteResult
from app.eval.profiles import EvalProfile, EvalProfileNotImplementedError, parse_eval_profile
from app.eval.reporting import suite_result_to_dict
from app.eval.runner import EvaluationRunner

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NL2SQL Evaluation")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument(
        "--profile", 
        type=str,
        default=EvalProfile.SMOKE.value,
        help="Evaluation profile to run (smoke, golden, large_schema)"
    )
    return parser

def build_runner() -> EvaluationRunner:
    # Use deterministic fake eval pipeline by default; no real LLM/API calls.
    return EvaluationRunner(pipeline_factory=lambda store: DeterministicFakePipeline(store))

def print_text_report(suite_result: EvalSuiteResult) -> None:
    print("Evaluation Summary")
    print("-" * 18)
    print(f"Profile: {suite_result.profile}")
    print(f"Total cases: {suite_result.total_cases}")
    print(f"Passed: {suite_result.passed}")
    print(f"Failed: {suite_result.failed}")
    print(f"Pass rate: {suite_result.pass_rate * 100:.2f}%")
    print()

    for r in suite_result.results:
        status = "[PASS]" if r.passed else "[FAIL]"
        print(f"{status} {r.case_id}")

        if r.error_type:
            print(f"  Error type: {r.error_type}")

        if r.error_message:
            print(f"  Error message: {r.error_message}")

        for c in r.checks:
            if c.passed:
                print(f"  PASS {c.name}")
            else:
                msg = c.message if c.message else "Failed"
                print(f"  FAIL {c.name}: {msg}")
        print()

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        profile_enum = parse_eval_profile(args.profile)
        cases = get_cases_for_profile(profile_enum)
    except EvalProfileNotImplementedError as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    runner = build_runner()
    suite_result = runner.run_suite(cases, profile=profile_enum)

    if args.json:
        output = suite_result_to_dict(suite_result)
        print(json.dumps(output, indent=2))
        return 1 if suite_result.failed > 0 else 0

    print_text_report(suite_result)
    return 1 if suite_result.failed > 0 else 0

if __name__ == "__main__":
    raise SystemExit(main())
