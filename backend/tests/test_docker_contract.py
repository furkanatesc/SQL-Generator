import os

def test_dockerfile_exists_and_conforms_to_contract():
    dockerfile_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Dockerfile"
    )
    assert os.path.exists(dockerfile_path), "Dockerfile does not exist at expected location"
    
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "FROM python:3.11-slim" in content, "Dockerfile should use python:3.11-slim as base image"
    assert "WORKDIR /app" in content, "Dockerfile should set working directory to /app"
    assert "requirements.txt" in content, "Dockerfile should refer to requirements.txt"
    assert "COPY app /app/app" in content, "Dockerfile should copy the app directory"
    assert "USER app" in content, "Dockerfile should run under non-root app user"
    assert "EXPOSE 8000" in content, "Dockerfile should expose port 8000"
    
    # Check CMD signature
    assert 'CMD ["uvicorn", "app.main:app"' in content, "Dockerfile should start uvicorn app.main:app"

def test_dockerignore_exists_and_excludes_local_artifacts():
    dockerignore_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".dockerignore"
    )
    assert os.path.exists(dockerignore_path), ".dockerignore does not exist at expected location"
    
    with open(dockerignore_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.read().splitlines()]
        
    assert ".env" in lines, ".dockerignore must exclude local env files"
    assert "uploads/" in lines or "uploads" in lines, ".dockerignore must exclude uploads"
    assert "tests/" in lines or "tests" in lines, ".dockerignore must exclude test files"
    assert "venv/" in lines or "venv" in lines, ".dockerignore must exclude local virtual environments"
    assert ".venv/" in lines or ".venv" in lines, ".dockerignore must exclude local virtual environments"
