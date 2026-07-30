from app.debug_bundle.projectors import (
    project_job, project_sql, project_schema, project_meta,
)


def test_project_job_allow_lists_and_flags_presence():
    job = {"id": "j", "status": "completed", "dialect": "postgres",
           "error_code": None, "natural_query": "musteriler", "file_path": None,
           "result_sql": "SELECT 1", "secret_col": "LEAK"}
    info = project_job(job).to_payload()
    assert info["has_natural_query"] is True
    assert info["has_excel_input"] is False
    assert info["result_sql_present"] is True
    # Ham metin ve whitelisted olmayan alan sizmaz.
    assert "natural_query" not in info and "result_sql" not in info
    assert "secret_col" not in info


def test_project_sql_reads_allow_listed_fields():
    payload = {"payload": {"generated_sql": "SELECT 1", "last_generated_sql": "SELECT 1",
                           "sql_valid": True, "attempts": [{"n": 1}],
                           "sql_validation_errors": []}}
    out = project_sql(payload).to_payload()
    assert out["generated_sql"] == "SELECT 1"
    assert out["sql_valid"] is True
    assert out["attempts"] == [{"n": 1}]


def test_project_sql_reads_root_mirrored_fields():
    # serialize_trace_for_debug payload anahtarlarini root'a da yansitir.
    payload = {"generated_sql": "SELECT 2", "sql_valid": False,
               "attempts": [], "sql_validation_errors": [{"type": "missing_column"}]}
    out = project_sql(payload).to_payload()
    assert out["generated_sql"] == "SELECT 2"
    assert out["sql_valid"] is False


def test_project_sql_none_when_no_debug_trace():
    assert project_sql(None) is None
    assert project_sql({}) is None


def test_project_schema_from_end_to_end_retrieval_span():
    trace = {"spans": [
        {"stage": "retrieval", "detail": {"candidates": [
            {"object_id": "orders", "object_type": "table", "schema_hash": "h1"},
            {"object_id": "orders.id", "object_type": "column", "schema_hash": "h1"},
            {"object_id": "customers", "object_type": "table", "schema_hash": "h1"}]}}]}
    out = project_schema(trace, None).to_payload()
    assert out["selected_tables"] == ["customers", "orders"]   # sirali
    assert out["schema_hash"] == "h1"
    assert out["table_count"] == 2


def test_project_schema_falls_back_to_replay_observed_tables():
    replay = {"retrieval": {"observed_tables": ["orders"]}}
    out = project_schema(None, replay).to_payload()
    assert out["selected_tables"] == ["orders"]


def test_project_schema_none_when_nothing_available():
    assert project_schema(None, None) is None
    assert project_schema({"spans": []}, {"retrieval": None}) is None


def test_project_meta_reads_trace_version_from_payload():
    meta = project_meta({"version": "end_to_end_trace_v1"},
                        {"version": "query_replay_v1"}, "postgres").to_payload()
    assert meta["bundle_contract_version"] == "debug_bundle_v1"
    assert meta["replay_contract_version"] == "query_replay_v1"
    assert meta["trace_contract_version"] == "end_to_end_trace_v1"
    assert meta["dialect"] == "postgres"


def test_project_meta_trace_version_none_without_trace():
    meta = project_meta(None, None, "postgres").to_payload()
    assert meta["trace_contract_version"] is None
    assert meta["replay_contract_version"] is None
