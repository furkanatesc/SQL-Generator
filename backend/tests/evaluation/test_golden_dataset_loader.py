import os
import tempfile
import pytest

from app.evaluation.golden_dataset_contract import (
    SQLGoldenDatasetContractError,
    SQLGoldenDatasetManifest,
)
from app.evaluation.golden_dataset_loader import SQLGoldenDatasetLoader

VALID_MANIFEST_JSON = """
{
  "version": "sql_golden_dataset_v2",
  "cases": [
    {
      "case_id": "case_02",
      "question": "Q2",
      "dialect": "sqlite",
      "schema_snapshot_id": "snap_01",
      "fixture_ref": "fix_01",
      "gold_sql": "SELECT 2;",
      "tier": "core_regression"
    },
    {
      "case_id": "case_01",
      "question": "Q1",
      "dialect": "postgresql",
      "schema_snapshot_id": "snap_01",
      "fixture_ref": "fix_01",
      "gold_sql": "SELECT 1;",
      "tier": "p0_canary",
      "owner": "john"
    }
  ]
}
"""

VALID_MANIFEST_YAML = """
version: sql_golden_dataset_v2
cases:
  - case_id: case_02
    question: Q2
    dialect: sqlite
    schema_snapshot_id: snap_01
    fixture_ref: fix_01
    gold_sql: SELECT 2;
    tier: core_regression
  - case_id: case_01
    question: Q1
    dialect: postgresql
    schema_snapshot_id: snap_01
    fixture_ref: fix_01
    gold_sql: SELECT 1;
    tier: p0_canary
    owner: john
"""


def test_loader_loads_manifest_without_network():
    # Test loading JSON string
    manifest = SQLGoldenDatasetLoader.load_from_json(VALID_MANIFEST_JSON)
    assert isinstance(manifest, SQLGoldenDatasetManifest)
    assert len(manifest.cases) == 2
    # Check deterministic sorting by case_id
    assert manifest.cases[0].case_id == "case_01"
    assert manifest.cases[1].case_id == "case_02"

    # Test loading YAML string
    manifest_yaml = SQLGoldenDatasetLoader.load_from_yaml(VALID_MANIFEST_YAML)
    assert isinstance(manifest_yaml, SQLGoldenDatasetManifest)
    assert len(manifest_yaml.cases) == 2
    assert manifest_yaml.cases[0].case_id == "case_01"
    assert manifest_yaml.cases[1].case_id == "case_02"

    # Test loading from local temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "manifest.json")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(VALID_MANIFEST_JSON)
        
        manifest_file = SQLGoldenDatasetLoader.load_from_file(json_path)
        assert len(manifest_file.cases) == 2

    # Test network URLs are rejected immediately
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetLoader.load_from_file("https://example.com/manifest.json")
    assert "Network paths are not allowed" in str(exc_info.value)


@pytest.mark.parametrize("invalid_content, error_snippet", [
    # Duplicate case_ids
    (
      '{"version": "sql_golden_dataset_v2", "cases": [{"case_id": "c1", "question": "Q", "dialect": "sqlite", "schema_snapshot_id": "s", "fixture_ref": "f", "gold_sql": "S"}, {"case_id": "c1", "question": "Q", "dialect": "sqlite", "schema_snapshot_id": "s", "fixture_ref": "f", "gold_sql": "S"}]}',
      "Duplicate case ID found"
    ),
    # Unknown field (strict validation check)
    (
      '{"version": "sql_golden_dataset_v2", "cases": [{"case_id": "c1", "question": "Q", "dialect": "sqlite", "schema_snapshot_id": "s", "fixture_ref": "f", "gold_sql": "S", "unknown_extra_field": "val"}]}',
      "Unknown field 'unknown_extra_field'"
    ),
    # Incorrect version
    (
      '{"version": "sql_golden_dataset_v1", "cases": []}',
      "Invalid manifest version"
    ),
    # Invalid JSON format
    (
      '{"version": "sql_golden_dataset_v2", "cases": [invalid json',
      "Invalid JSON format"
    ),
    # Missing required field
    (
      '{"version": "sql_golden_dataset_v2", "cases": [{"question": "Q", "dialect": "sqlite", "schema_snapshot_id": "s", "fixture_ref": "f", "gold_sql": "S"}]}',
      "case_id cannot be empty"
    ),
])
def test_loader_rejects_nondeterministic_or_invalid_manifest(invalid_content, error_snippet):
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetLoader.load_from_json(invalid_content)
    assert error_snippet in str(exc_info.value)


def test_loader_rejects_missing_manifest_version():
    content = '{"cases": []}'
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetLoader.load_from_json(content)
    assert "Manifest data must contain a 'version' field" in str(exc_info.value)


def test_loader_missing_required_fields_error_order_is_deterministic():
    # If case_id and question are both missing, case_id should be checked first
    raw_data = {
        "version": "sql_golden_dataset_v2",
        "cases": [
            {
                # case_id and question are missing
                "dialect": "sqlite",
                "schema_snapshot_id": "snap_01",
                "fixture_ref": "fix_01",
                "gold_sql": "SELECT 1;",
            }
        ]
    }
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetLoader.load_from_dict(raw_data)
    assert "case_id cannot be empty" in str(exc_info.value)

    # If question and dialect are missing (but case_id is present), question should be checked next
    raw_data_2 = {
        "version": "sql_golden_dataset_v2",
        "cases": [
            {
                "case_id": "c1",
                # question and dialect are missing
                "schema_snapshot_id": "snap_01",
                "fixture_ref": "fix_01",
                "gold_sql": "SELECT 1;",
            }
        ]
    }
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetLoader.load_from_dict(raw_data_2)
    assert "question cannot be empty" in str(exc_info.value)
