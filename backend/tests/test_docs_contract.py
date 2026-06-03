import os

def test_documentation_files_exist_and_conform_to_contract():
    # Find the repository root directory relative to this test file
    repo_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
    
    # Define documentation file paths
    production_runbook_path = os.path.join(repo_root, "docs", "production-runbook.md")
    env_contract_path = os.path.join(repo_root, "docs", "env-contract.md")
    deployment_checklist_path = os.path.join(repo_root, "docs", "deployment-acceptance-checklist.md")
    release_verification_path = os.path.join(repo_root, "docs", "release-verification.md")
    
    # Assert files exist on disk
    assert os.path.exists(production_runbook_path), f"Production runbook file not found at: {production_runbook_path}"
    assert os.path.exists(env_contract_path), f"Environment contract file not found at: {env_contract_path}"
    assert os.path.exists(deployment_checklist_path), f"Deployment acceptance checklist file not found at: {deployment_checklist_path}"
    assert os.path.exists(release_verification_path), f"Release verification file not found at: {release_verification_path}"

    # Read checklist content and verify contract strings
    with open(deployment_checklist_path, "r", encoding="utf-8") as f:
        checklist_content = f.read().lower()

    required_checklist_strings = [
        "nl2sql_api_key",
        "nl2sql_environment",
        "nl2sql_cors_allow_origins",
        "nl2sql_debug_endpoints_enabled",
        "nl2sql_upload_dir",
        "/health",
        "startup_critical_warnings_count",
        "docker image build",
        "runtime smoke test",
        "no wildcard cors in production",
        "debug endpoints disabled in production",
    ]
    for s in required_checklist_strings:
        assert s in checklist_content, f"Expected '{s}' to be present in deployment-acceptance-checklist.md"

    # Read release verification content and verify contract strings
    with open(release_verification_path, "r", encoding="utf-8") as f:
        verification_content = f.read().lower()

    required_verification_strings = [
        "pytest",
        "docker build",
        "docker run",
        "curl -fss http://localhost:8000/health",
        "docker logs",
        "docker rm -f",
        "startup_critical_warnings_count",
        "api_key_configured",
        "raw secrets not exposed",
    ]
    for s in required_verification_strings:
        assert s in verification_content, f"Expected '{s}' to be present in release-verification.md"
