import os
import pytest

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")

def test_rc_verification_evidence_contract():
    file_path = os.path.join(DOCS_DIR, "product-v1-rc-verification.md")
    assert os.path.exists(file_path), "product-v1-rc-verification.md is missing"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_evidence_sections = [
        "Backend CI green",
        "Docker build passes",
        "Docker smoke passes",
        "golden eval profile passes",
        "smoke eval profile passes",
        "Text-to-SQL happy path evidence",
        "SQL validation/error path evidence",
        "\"status\": \"ok\"",
        "\"error_code\": \"UNSAFE_QUERY_DETECTED\"",
        "Known Limitations Final Review",
        "No multi-tenant auth"
    ]
    
    for item in required_evidence_sections:
        assert item in content, f"RC verification document is missing critical evidence: '{item}'"
