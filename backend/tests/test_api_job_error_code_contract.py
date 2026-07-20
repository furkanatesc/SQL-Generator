"""Sprint 27.2.1 — error_code'un job runner sınırından geçmesi.

Mevcut test_api_safe_failure_response_contract.py'deki mock desenini izler:
app.database.* fonksiyonları patch'lenir, process_job_pipeline doğrudan çağrılır.
"""
from unittest.mock import patch

from app.errors import ErrorCode
from app.main import process_job_pipeline

FAKE_JOB_PENDING = {
    "id": "job-123",
    "status": "pending",
    "file_path": None,
    "natural_query": "tüm hastaları getir",
    "previous_sql": None,
    "dialect": "postgres",
}


@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_taksonomik_hata_error_code_string_olarak_persist_edilir(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    mock_run_pipeline.return_value = {
        "success": False,
        "error": "Girdi yorumlanamadı",
        "error_code": ErrorCode.INPUT_ERROR,
        "generated_sql": "",
        "attempts": [],
    }

    process_job_pipeline("job-123")

    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[1] == "failed"
    assert kwargs["error_code"] == "input_error"
    # Sınırda ham string taşınır, enum değil (API sözleşmesi tipsiz string).
    assert type(kwargs["error_code"]) is str


@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_error_code_yoksa_none_gecilir(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    # Kodsuz başarısızlık (eski/kısmi sonuç sözlüğü)
    mock_run_pipeline.return_value = {
        "success": False,
        "error": "Bilinmeyen hata",
        "error_code": None,
        "generated_sql": "",
        "attempts": [],
    }

    process_job_pipeline("job-123")

    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[1] == "failed"
    assert kwargs["error_code"] is None


@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_beklenmeyen_exception_error_code_birakmaz(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    # INTERNAL kategorisinin taksonomi kodu YOKTUR (registry tasarımı);
    # beklenmeyen job-runner exception'ı error_code'u NULL bırakmalı.
    mock_run_pipeline.side_effect = RuntimeError("beklenmeyen çökme")

    process_job_pipeline("job-123")

    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[1] == "failed"
    assert kwargs.get("error_code") is None


@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_basarili_job_error_code_yazmaz(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    mock_run_pipeline.return_value = {
        "success": True,
        "error": None,
        "error_code": None,
        "generated_sql": "SELECT 1",
        "attempts": [],
    }

    process_job_pipeline("job-123")

    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[1] == "completed"
    assert "error_code" not in kwargs


@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_ham_string_error_code_tolere_edilir_ve_persist_edilir(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    # Pipeline üretim kodu değişirse, ham string error_code gönderilebilir.
    # Bu test, getattr defensive programlamasını pin'ler: .value çıkarmak
    # yerine olduğu gibi geç; AttributeError'dan kaçın.
    mock_run_pipeline.return_value = {
        "success": False,
        "error": "Girdi yorumlanamadı",
        "error_code": "input_error",  # String, not ErrorCode enum
        "generated_sql": "",
        "attempts": [],
    }

    process_job_pipeline("job-123")

    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[1] == "failed"
    assert kwargs["error_code"] == "input_error"
    assert type(kwargs["error_code"]) is str


# --- API yüzeyi: error_code response'ta görünür ---

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


def test_job_detail_response_error_code_alanini_tasir():
    from app.database import create_job, update_job_status

    job = create_job("job-errcode-api", natural_query="test")
    update_job_status(job["id"], "failed",
                      error_message="Sözdizimi hatası",
                      error_code="syntax_error")

    res = client.get(f"/api/jobs/{job['id']}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["error_code"] == "syntax_error"


def test_job_detail_error_code_yoksa_null_doner():
    from app.database import create_job

    job = create_job("job-errcode-api-null", natural_query="test")

    res = client.get(f"/api/jobs/{job['id']}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["error_code"] is None
