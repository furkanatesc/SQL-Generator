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
    
    # Assert files exist on disk
    assert os.path.exists(production_runbook_path), f"Production runbook file not found at: {production_runbook_path}"
    assert os.path.exists(env_contract_path), f"Environment contract file not found at: {env_contract_path}"
