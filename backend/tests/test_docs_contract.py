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
