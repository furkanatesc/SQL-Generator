"""feedback tablosu persist davranışı (Sprint 27.3): append-only, job-bazlı okuma."""
import uuid

import pytest

from app.database import (
    create_feedback,
    create_job,
    get_feedback,
    get_feedback_for_job,
    init_db,
)


@pytest.fixture
def job_id():
    jid = f"test-fb-{uuid.uuid4()}"
    create_job(jid, natural_query="test sorgusu")
    return jid


def test_create_feedback_satiri_persist_eder_ve_doner(job_id):
    fid = str(uuid.uuid4())
    row = create_feedback(fid, job_id, "incorrect", category="wrong_filter",
                          note="tarih filtresi eksik")
    assert row["id"] == fid
    assert row["job_id"] == job_id
    assert row["verdict"] == "incorrect"
    assert row["category"] == "wrong_filter"
    assert row["note"] == "tarih filtresi eksik"
    assert row["corrected_sql"] is None
    assert row["created_at"]  # dolu
    # Ayrı okuma da aynı satırı görür.
    assert get_feedback(fid) == row


def test_correct_verdict_kategorisiz_saklanir(job_id):
    fid = str(uuid.uuid4())
    row = create_feedback(fid, job_id, "correct")
    assert row["verdict"] == "correct"
    assert row["category"] is None
    assert row["corrected_sql"] is None


def test_append_only_ayni_joba_coklu_satir_kronolojik(job_id):
    f1 = create_feedback(str(uuid.uuid4()), job_id, "incorrect",
                         category="wrong_table")
    f2 = create_feedback(str(uuid.uuid4()), job_id, "incorrect",
                         category="wrong_join", corrected_sql="SELECT 1")
    rows = get_feedback_for_job(job_id)
    assert len(rows) == 2
    # created_at ASC — ekleme sırası korunur.
    assert [r["id"] for r in rows] == [f1["id"], f2["id"]]


def test_bilinmeyen_job_bos_liste(job_id):
    assert get_feedback_for_job(f"yok-{uuid.uuid4()}") == []


def test_init_db_idempotent():
    # İki kez çağrılınca feedback tablosu/index bir kez kurulur, hata vermez.
    init_db()
    init_db()
    fid = str(uuid.uuid4())
    jid = f"test-fb-idem-{uuid.uuid4()}"
    create_job(jid, natural_query="x")
    create_feedback(fid, jid, "correct")
    assert get_feedback(fid)["verdict"] == "correct"
