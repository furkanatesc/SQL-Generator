import json
import os
import yaml
from typing import Any, Dict

from .golden_dataset_contract import (
    SQL_GOLDEN_DATASET_VERSION,
    SQLGoldenDatasetCase,
    SQLGoldenDatasetContractError,
    SQLGoldenDatasetManifest,
)


class SQLGoldenDatasetLoader:
    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> SQLGoldenDatasetManifest:
        """Loads and validates a manifest from a dictionary."""
        if not isinstance(data, dict):
            raise SQLGoldenDatasetContractError("Manifest data must be a dictionary")
        
        version = data.get("version", SQL_GOLDEN_DATASET_VERSION)
        raw_cases = data.get("cases")
        
        if raw_cases is None:
            raise SQLGoldenDatasetContractError("Manifest data must contain a 'cases' field")
            
        if not isinstance(raw_cases, list):
            raise SQLGoldenDatasetContractError("Manifest 'cases' field must be a list")
            
        cases_list = []
        # Inspect valid fields of SQLGoldenDatasetCase to prevent unknown keys
        from dataclasses import fields
        valid_fields = {f.name for f in fields(SQLGoldenDatasetCase)}
        
        required_fields = {
            "case_id",
            "question",
            "dialect",
            "schema_snapshot_id",
            "fixture_ref",
            "gold_sql",
        }

        for raw_case in raw_cases:
            if not isinstance(raw_case, dict):
                raise SQLGoldenDatasetContractError("Each case in manifest must be a dictionary")
            
            # Check for extra/unknown fields to enforce strict contract schema
            for k in raw_case.keys():
                if k not in valid_fields:
                    raise SQLGoldenDatasetContractError(f"Unknown field '{k}' in case schema")
            
            # Check for missing required fields explicitly
            for rf in required_fields:
                if rf not in raw_case or raw_case[rf] is None:
                    raise SQLGoldenDatasetContractError(f"{rf} cannot be empty")
            
            # Reconstruct case by unpacking.
            try:
                case = SQLGoldenDatasetCase(**raw_case)
                cases_list.append(case)
            except TypeError as e:
                raise SQLGoldenDatasetContractError(f"Invalid case schema structure: {e}")
                
        return SQLGoldenDatasetManifest(version=version, cases=tuple(cases_list))

    @classmethod
    def load_from_json(cls, json_str: str) -> SQLGoldenDatasetManifest:
        """Loads and validates a manifest from a JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise SQLGoldenDatasetContractError(f"Invalid JSON format: {e}")
        return cls.load_from_dict(data)

    @classmethod
    def load_from_yaml(cls, yaml_str: str) -> SQLGoldenDatasetManifest:
        """Loads and validates a manifest from a YAML string."""
        try:
            data = yaml.safe_load(yaml_str)
        except Exception as e:
            raise SQLGoldenDatasetContractError(f"Invalid YAML format: {e}")
        return cls.load_from_dict(data)

    @classmethod
    def load_from_file(cls, filepath: str) -> SQLGoldenDatasetManifest:
        """Loads a manifest from a local file path. No network calls are made."""
        if not filepath:
            raise SQLGoldenDatasetContractError("Filepath cannot be empty")
            
        # Ensure we do not make network calls (no url-like paths allowed)
        if filepath.startswith(("http://", "https://", "ftp://")):
            raise SQLGoldenDatasetContractError("Network paths are not allowed in golden dataset loader")
            
        if not os.path.exists(filepath):
            raise SQLGoldenDatasetContractError(f"File not found: {filepath}")
            
        _, ext = os.path.splitext(filepath.lower())
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise SQLGoldenDatasetContractError(f"Failed to read file: {e}")
            
        if ext in (".yaml", ".yml"):
            return cls.load_from_yaml(content)
        elif ext == ".json":
            return cls.load_from_json(content)
        else:
            # Try parsing as JSON first, then YAML
            try:
                return cls.load_from_json(content)
            except SQLGoldenDatasetContractError:
                return cls.load_from_yaml(content)
