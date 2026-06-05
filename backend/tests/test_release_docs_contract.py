import os
import pytest

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")

REQUIRED_TERMS = [
    "/health",
    "/ready",
    "NL2SQL_API_KEY",
    "NL2SQL_ENVIRONMENT",
    "NL2SQL_CORS_ALLOW_ORIGINS",
    "docker build",
    "docker run",
    "rollback",
    "smoke test",
    "Backend CI green"
]

@pytest.mark.parametrize("doc_file", [
    "production-release-runbook.md",
    "production-smoke-checklist.md"
])
def test_docs_contain_critical_contracts(doc_file):
    file_path = os.path.join(DOCS_DIR, doc_file)
    assert os.path.exists(file_path), f"Required documentation file missing: {doc_file}"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    for term in REQUIRED_TERMS:
        assert term in content, f"Critical term '{term}' is missing from {doc_file}"
