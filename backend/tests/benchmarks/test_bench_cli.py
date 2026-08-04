import json
import benchmarks.bench_cli as cli


def _point(tmp_path, monkeypatch):
    p = tmp_path / "history.json"
    monkeypatch.setattr(cli, "BASELINE_PATH", p)
    return p


def test_update_baseline_then_gate_clean(tmp_path, monkeypatch, capsys):
    _point(tmp_path, monkeypatch)
    assert cli.main(["--update-baseline", "--scales", "30", "--seed", "7"]) == 0
    capsys.readouterr()
    # gate against the just-written baseline -> clean (deterministic metrics match)
    assert cli.main(["--gate", "--scales", "30", "--seed", "7"]) == 0


def test_gate_bootstrap_when_no_baseline(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    assert cli.main(["--gate", "--scales", "30", "--seed", "7"]) == 0


def test_gate_detects_drift(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    # write a baseline whose deterministic metrics cannot match a real run
    fake = {"schema_version": "large_schema_benchmark_v1", "generator_params": {"seed": 7},
            "metrics": [{"target": "schema_validation", "scale": 30,
                         "deterministic": {"tables": 999}, "wall_ms": 1.0}]}
    p.write_text(json.dumps([fake]))
    assert cli.main(["--gate", "--scales", "30", "--seed", "7"]) == 1


def test_gate_malformed_baseline_returns_2(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    p.write_text("{ this is not valid json")
    assert cli.main(["--gate", "--scales", "30", "--seed", "7"]) == 2


def test_update_baseline_is_append_only(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    cli.main(["--update-baseline", "--scales", "30", "--seed", "7"])
    cli.main(["--update-baseline", "--scales", "30", "--seed", "7"])
    history = json.loads(p.read_text())
    assert isinstance(history, list) and len(history) == 2
