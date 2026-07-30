from app.debug_bundle import (
    BUNDLE_CONTRACT_VERSION, DebugBundle, BundleJobInfo, BundleSqlInfo,
    BundleSchemaInfo, BundleMeta,
)


def _sample() -> DebugBundle:
    return DebugBundle(
        version=BUNDLE_CONTRACT_VERSION,
        job_id="job-1",
        job=BundleJobInfo(status="completed", dialect="postgres", error_code=None,
                          has_natural_query=True, has_excel_input=False,
                          result_sql_present=True),
        trace={"version": "end_to_end_trace_v1", "spans": []},
        sql=BundleSqlInfo(generated_sql="SELECT 1", last_generated_sql="SELECT 1",
                          sql_valid=True, attempts=(), sql_validation_errors=()),
        replay={"version": "query_replay_v1", "verdict": "identical"},
        schema=BundleSchemaInfo(selected_tables=("orders",), schema_hash="h1", table_count=1),
        meta=BundleMeta(bundle_contract_version=BUNDLE_CONTRACT_VERSION,
                        replay_contract_version="query_replay_v1",
                        trace_contract_version="end_to_end_trace_v1", dialect="postgres"),
    )


def test_to_payload_is_json_safe_and_shaped():
    import json
    p = _sample().to_payload()
    json.dumps(p)  # raises if not JSON-safe
    assert p["version"] == "debug_bundle_v1"
    assert p["job_id"] == "job-1"
    assert p["job"]["has_natural_query"] is True
    assert p["schema"]["selected_tables"] == ["orders"]   # tuple -> list
    assert p["sql"]["sql_valid"] is True
    assert set(p.keys()) == {"version", "job_id", "job", "trace", "sql", "replay", "schema", "meta"}


def test_to_payload_is_deterministic():
    assert _sample().to_payload() == _sample().to_payload()


def test_optional_sections_serialize_as_none():
    b = DebugBundle(version=BUNDLE_CONTRACT_VERSION, job_id="j",
                    job=BundleJobInfo(), trace=None, sql=None, replay=None,
                    schema=None, meta=None)
    p = b.to_payload()
    assert p["trace"] is None and p["sql"] is None and p["replay"] is None
    assert p["schema"] is None and p["meta"] is None
