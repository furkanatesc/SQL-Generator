import os
import pytest

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")

def test_rc_checklist_contract():
    file_path = os.path.join(DOCS_DIR, "product-v1-rc-checklist.md")
    assert os.path.exists(file_path), "product-v1-rc-checklist.md is missing"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_checklist_items = [
        "Backend CI green",
        "Docker build passes",
        "Docker smoke passes",
        "/health returns 200",
        "/ready returns 200",
        "golden eval profile passes",
        "smoke eval profile passes",
        "text-to-SQL happy path verified",
        "SQL validation/error path verified",
        "auth/security contract verified",
        "rollback runbook verified"
    ]
    
    for item in required_checklist_items:
        assert item in content, f"RC checklist is missing critical gate: '{item}'"

def test_known_limitations_contract():
    file_path = os.path.join(DOCS_DIR, "product-v1-known-limitations.md")
    assert os.path.exists(file_path), "product-v1-known-limitations.md is missing"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_limitations = [
        "No multi-tenant auth",
        "No full RBAC",
        "No managed cloud deployment manifest",
        "No external APM/tracing backend",
        "SQLite-backed default deployment profile"
    ]
    
    for item in required_limitations:
        assert item in content, f"Known limitations document is hiding or missing constraint: '{item}'"
