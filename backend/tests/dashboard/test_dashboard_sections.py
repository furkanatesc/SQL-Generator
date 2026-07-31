from datetime import datetime, timezone
from app.dashboard import top_errors, summarize_feedback, shape_recent


def test_top_errors_sorted_desc_then_code_asc_with_category():
    metrics = {"errors": {"by_code": {"missing_column": 2, "unsafe_dml_keyword": 5,
                                      "input_error": 2}}}
    out = [e.to_payload() for e in top_errors(metrics, 2)]
    # sayiya gore azalan: unsafe(5) once; sonra esitlikte kod artan: input_error < missing_column
    assert out[0] == {"code": "unsafe_dml_keyword", "category": "security", "count": 5}
    assert out[1]["code"] == "input_error"
    assert len(out) == 2   # top_n kesme


def test_top_errors_unknown_code_bucket():
    out = top_errors({"errors": {"by_code": {"not_a_code_xyz": 1}}}, 5)
    assert out[0].category == "unknown"


def test_top_errors_empty():
    assert top_errors({"errors": {"by_code": {}}}, 5) == ()
    assert top_errors({}, 5) == ()


def test_summarize_feedback_counts_and_skips_none_category():
    rows = [
        {"verdict": "incorrect", "category": "wrong_columns"},
        {"verdict": "incorrect", "category": None},   # correct verdict -> kategori None
        {"verdict": "correct", "category": None},
    ]
    fs = summarize_feedback(rows).to_payload()
    assert fs["total"] == 3
    assert fs["by_verdict"] == {"correct": 1, "incorrect": 2}
    assert fs["by_category"] == {"wrong_columns": 1}   # None atlandi


def test_summarize_feedback_empty():
    fs = summarize_feedback([]).to_payload()
    assert fs == {"total": 0, "by_verdict": {}, "by_category": {}}


def test_shape_recent_limit_and_fields():
    def _item(i):
        return (datetime(2026, 7, 31, i, tzinfo=timezone.utc),
                {"job_id": f"j{i}", "trace_id": f"t{i}", "terminal_status": "completed",
                 "dialect": "postgres", "total_duration_ms": i})
    items = [_item(3), _item(2), _item(1)]   # DESC verilmis
    out = [r.to_payload() for r in shape_recent(items, 2)]
    assert len(out) == 2
    assert out[0]["job_id"] == "j3"
    assert out[0]["created_at"] == "2026-07-31T03:00:00+00:00"
    assert out[1]["job_id"] == "j2"
