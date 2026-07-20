"""jobs tablosu persist davranışı: error_code kolonu + dinamik SET-clause.

Sprint 27.2.1. Bu testlerin çoğu MEVCUT davranışı dondurur: dinamik-SET
refactor'ünün eski if/elif merdiveniyle bit-bit aynı sonucu verdiğini kanıtlar.
"""
import uuid

import pytest

from app.database import create_job, get_job, init_db, update_job_status


@pytest.fixture
def job_id():
    jid = f"test-{uuid.uuid4()}"
    create_job(jid, natural_query="test sorgusu")
    return jid


def test_yeni_job_error_code_none_baslar(job_id):
    assert get_job(job_id)["error_code"] is None


def test_error_code_yazilir_ve_okunur(job_id):
    update_job_status(job_id, "failed",
                      error_message="Sözdizimi hatası",
                      error_code="syntax_error")
    job = get_job(job_id)
    assert job["status"] == "failed"
    assert job["error_message"] == "Sözdizimi hatası"
    assert job["error_code"] == "syntax_error"


def test_yalniz_status_guncellenir_diger_alanlar_korunur(job_id):
    # Davranış koruma: eski if/elif'in "else" dalı
    update_job_status(job_id, "failed", error_message="ilk hata",
                      error_code="input_error")
    update_job_status(job_id, "processing")
    job = get_job(job_id)
    assert job["status"] == "processing"
    assert job["error_message"] == "ilk hata"   # None geçilince SET edilmez
    assert job["error_code"] == "input_error"


def test_result_sql_dali_error_alanlarina_dokunmaz(job_id):
    update_job_status(job_id, "failed", error_message="hata",
                      error_code="input_error")
    update_job_status(job_id, "completed", result_sql="SELECT 1")
    job = get_job(job_id)
    assert job["status"] == "completed"
    assert job["result_sql"] == "SELECT 1"
    assert job["error_message"] == "hata"
    assert job["error_code"] == "input_error"


def test_result_sql_ve_error_message_birlikte(job_id):
    # Davranış koruma: eski if/elif'in ilk dalı
    update_job_status(job_id, "failed", result_sql="SELECT 1",
                      error_message="yine de hata")
    job = get_job(job_id)
    assert job["result_sql"] == "SELECT 1"
    assert job["error_message"] == "yine de hata"
    assert job["error_code"] is None


def test_update_job_status_guncellenmis_job_dondurur(job_id):
    returned = update_job_status(job_id, "failed", error_code="syntax_error")
    assert returned["error_code"] == "syntax_error"
    assert returned == get_job(job_id)


def test_updated_at_her_dalda_yazilir(job_id):
    # updated_at eski if/elif'in DÖRT dalında da SET ediliyordu; dinamik
    # refactor'de de koşulsuz SET edilmeli.
    for kwargs in ({}, {"result_sql": "SELECT 1"},
                   {"error_message": "hata"}, {"error_code": "input_error"}):
        update_job_status(job_id, "processing", **kwargs)
        assert get_job(job_id)["updated_at"] is not None


def test_init_db_idempotent_error_code_kolonu_bir_kez_eklenir():
    # init_db conftest'te zaten bir kez koştu; tekrar koşmak patlamamalı
    init_db()
    init_db()
    jid = f"test-{uuid.uuid4()}"
    create_job(jid)
    update_job_status(jid, "failed", error_code="input_error")
    assert get_job(jid)["error_code"] == "input_error"
