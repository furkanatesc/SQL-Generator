import os
import pytest

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")

def test_release_decision_contract():
    file_path = os.path.join(DOCS_DIR, "product-v1-release-decision.md")
    assert os.path.exists(file_path), "product-v1-release-decision.md is missing"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_decision_terms = [
        "release ready",
        "product-v1-rc-verification.md",
        "2f9e7e6",
        "tag v1.0.0",
        "Post-release monitoring checklist",
        "First 24 Hours Monitoring",
        "Future Monitoring Enhancements"
    ]
    
    for term in required_decision_terms:
        assert term in content, f"Release decision document missing critical reference: '{term}'"

def test_release_notes_contract():
    file_path = os.path.join(DOCS_DIR, "product-v1-release-notes.md")
    assert os.path.exists(file_path), "product-v1-release-notes.md is missing"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_notes_terms = [
        "Product V1",
        "Natural Language to SQL",
        "SQL Validation & Safety",
        "Known Limitations"
    ]
    
    for term in required_notes_terms:
        assert term in content, f"Release notes missing critical section: '{term}'"
