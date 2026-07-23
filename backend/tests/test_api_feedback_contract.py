"""Sprint 27.3 — POST /api/jobs/{id}/feedback API sözleşmesi.

Mevcut test_api_job_error_code_contract.py TestClient desenini izler.
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.database import create_job, get_feedback_for_job

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


def _new_job():
    return create_job(f"job-fb-{uuid.uuid4()}", natural_query="test")["id"]


def test_gecerli_incorrect_feedback_200_envelope():
    jid = _new_job()
    res = client.post(
        f"/api/jobs/{jid}/feedback",
        headers=HEADERS,
        json={"verdict": "incorrect", "category": "wrong_filter",
              "note": "tarih filtresi eksik"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    fb = body["feedback"]
    assert fb["id"]
    assert fb["job_id"] == jid
    assert fb["verdict"] == "incorrect"
    assert fb["category"] == "wrong_filter"
    assert fb["note"] == "tarih filtresi eksik"
    assert fb["corrected_sql"] is None
    assert fb["created_at"]


def test_correct_verdict_kategorisiz_200():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "correct"})
    assert res.status_code == 200
    assert res.json()["feedback"]["verdict"] == "correct"


def test_var_olmayan_job_404():
    res = client.post(f"/api/jobs/yok-{uuid.uuid4()}/feedback", headers=HEADERS,
                      json={"verdict": "correct"})
    assert res.status_code == 404
    # Global handler ErrorResponse envelope'una sarar.
    assert "error" in res.json()


def test_gecersiz_verdict_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "maybe"})
    assert res.status_code == 422


def test_invariant2_correct_plus_category_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "correct", "category": "wrong_table"})
    assert res.status_code == 422


def test_invariant2_correct_plus_corrected_sql_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "correct", "corrected_sql": "SELECT 1"})
    assert res.status_code == 422


def test_invariant3_other_note_yok_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "incorrect", "category": "other"})
    assert res.status_code == 422


def test_invariant3_other_bos_note_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "incorrect", "category": "other",
                            "note": "   "})
    assert res.status_code == 422


def test_other_note_ile_200():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "incorrect", "category": "other",
                            "note": "başka bir sebep"})
    assert res.status_code == 200


def test_note_asiri_uzun_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "incorrect", "category": "wrong_table",
                            "note": "x" * 2001})
    assert res.status_code == 422


def test_corrected_sql_asiri_uzun_422():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                      json={"verdict": "incorrect", "category": "wrong_join",
                            "corrected_sql": "x" * 5001})
    assert res.status_code == 422


def test_api_key_yoksa_403():
    jid = _new_job()
    res = client.post(f"/api/jobs/{jid}/feedback",
                      json={"verdict": "correct"})
    assert res.status_code == 403


def test_append_only_iki_post_iki_satir():
    jid = _new_job()
    client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                json={"verdict": "incorrect", "category": "wrong_table"})
    client.post(f"/api/jobs/{jid}/feedback", headers=HEADERS,
                json={"verdict": "incorrect", "category": "wrong_join"})
    rows = get_feedback_for_job(jid)
    assert len(rows) == 2
