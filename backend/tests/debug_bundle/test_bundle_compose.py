from app.debug_bundle import compose_bundle, BUNDLE_CONTRACT_VERSION


def _args():
    return dict(
        job={"id": "job-1", "status": "failed", "dialect": "postgres",
             "error_code": "sql_generation_exhausted", "natural_query": "x",
             "file_path": None, "result_sql": None},
        redacted_trace_payload={"version": "end_to_end_trace_v1", "spans": [
            {"stage": "retrieval", "detail": {"candidates": [
                {"object_id": "orders", "object_type": "table", "schema_hash": "h1"}]}}]},
        redacted_debug_trace_payload={"generated_sql": "SELECT 1", "sql_valid": False,
                                      "attempts": [], "sql_validation_errors": []},
        replay_payload={"version": "query_replay_v1", "verdict": "identical",
                        "retrieval": {"observed_tables": ["orders"]}},
        dialect="postgres",
    )


def test_compose_builds_full_bundle():
    p = compose_bundle(**_args()).to_payload()
    assert p["version"] == BUNDLE_CONTRACT_VERSION
    assert p["job_id"] == "job-1"
    assert p["job"]["error_code"] == "sql_generation_exhausted"
    assert p["job"]["has_natural_query"] is True
    assert p["sql"]["generated_sql"] == "SELECT 1"
    assert p["schema"]["selected_tables"] == ["orders"]
    assert p["replay"]["verdict"] == "identical"
    assert p["meta"]["trace_contract_version"] == "end_to_end_trace_v1"
    assert p["trace"]["spans"][0]["stage"] == "retrieval"


def test_compose_is_deterministic():
    assert compose_bundle(**_args()).to_payload() == compose_bundle(**_args()).to_payload()


def test_compose_handles_missing_trace_and_sql():
    a = _args()
    a["redacted_trace_payload"] = None
    a["redacted_debug_trace_payload"] = None
    p = compose_bundle(**a).to_payload()
    assert p["trace"] is None
    assert p["sql"] is None
    # schema replay observed_tables'a dayanir
    assert p["schema"]["selected_tables"] == ["orders"]
    assert p["meta"]["trace_contract_version"] is None
