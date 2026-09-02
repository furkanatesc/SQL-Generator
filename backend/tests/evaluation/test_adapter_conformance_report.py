"""Sprint 29.7 — conformance report emitter (Docker-free observability)."""
import json

from app.evaluation.adapter_conformance import (
    build_conformance_report,
    main,
    SQL_ADAPTER_CONFORMANCE_VERSION,
)


def test_report_has_one_entry_per_dialect():
    rep = build_conformance_report()
    assert rep["version"] == SQL_ADAPTER_CONFORMANCE_VERSION
    dialects = [d["dialect"] for d in rep["dialects"]]
    assert dialects == ["sqlite", "postgresql", "oracle", "mysql", "sqlserver"]


def test_report_capability_matrix_is_correct():
    rep = build_conformance_report()
    by = {d["dialect"]: d for d in rep["dialects"]}
    assert by["postgresql"]["accepts_explain_only"] is True
    assert by["sqlserver"]["accepts_explain_only"] is False
    assert by["sqlserver"]["capabilities"] == ["connection_ref", "read_only"]
    assert by["sqlite"]["capabilities"] == ["local_fixture", "read_only"]
    assert all(d["contract_conformance"]["ok"] for d in rep["dialects"])


def test_report_is_json_serialisable_and_deterministic():
    a = json.dumps(build_conformance_report(), sort_keys=True)
    b = json.dumps(build_conformance_report(), sort_keys=True)
    assert a == b
    json.loads(a)  # valid JSON


def test_main_report_json_writes_file(tmp_path, capsys):
    out = tmp_path / "conformance.json"
    rc = main(["report", "--json", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["version"] == SQL_ADAPTER_CONFORMANCE_VERSION
    assert len(data["dialects"]) == 5


def test_main_report_json_to_stdout(capsys):
    rc = main(["report", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == SQL_ADAPTER_CONFORMANCE_VERSION
