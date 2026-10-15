"""Run one NL→SQL job (Sprint 32.4).

Moved verbatim from `app.main.process_job_pipeline` so the same code runs in the API process
(inline mode) and in the worker process. `app.database` / `app.sql_pipeline` /
`app.trace.dependencies` are looked up at call time on purpose: existing tests patch them there.
Every log line is also persisted to `job_logs` so it survives restarts and can be streamed
from another process.
"""
import datetime
import logging
from typing import Callable, Dict, Optional

from app.jobs.queue_policy import is_transient_failure
from app.secret_resolver import resolve_secret

logger = logging.getLogger(__name__)

LogSink = Callable[[Dict], None]
FailureHook = Callable[[str, Optional[str], bool], bool]


def execute_job(
    job_id: str,
    request_id: Optional[str] = None,
    on_log: Optional[LogSink] = None,
    on_failure: Optional[FailureHook] = None,
) -> None:
    """`on_failure(error_message, error_code, transient)` returning True means the caller
    handled the failed pipeline result (e.g. scheduled a retry), so the job is not marked
    `failed` here. Unexpected exceptions (e.g. a missing LLM key) never go through it."""
    from app.sql_pipeline import SQLGenerationPipeline
    from app.database import get_job, update_job_status, get_config
    from app.jobs.repository import append_job_log

    job = get_job(job_id)
    if not job:
        return

    update_job_status(job_id, "processing")

    def log_callback(message: str, step: int):
        log_entry = {
            "message": message,
            "step": step,
            "timestamp": datetime.datetime.now().isoformat()
        }
        try:
            append_job_log(job_id, message, step)
        except Exception:  # noqa: BLE001 — logging must never break the job
            logger.exception("failed to persist job log for %s", job_id)
        if on_log is not None:
            on_log(log_entry)

    try:
        from app.trace.dependencies import get_trace_store
        pipeline = SQLGenerationPipeline(trace_store=get_trace_store())
        dialect = get_config("target_db_type") or "postgres"
        api_key = get_config("nvidia_api_key")

        # Eğer nvidia_api_key bulunamadıysa, varsayılan api_key'i dene
        if not api_key:
            api_key = get_config("api_key")

        file_path = job.get("file_path")
        natural_query = job.get("natural_query")

        # Eğer api key dev key ise ve çevre değişkeni de yoksa hata versin ki kullanıcı ayarlasın
        if (not api_key or api_key == "sqlgen_secret_dev_key") and not resolve_secret("NVIDIA_API_KEY"):
            raise ValueError(
                "NVIDIA API Anahtarı eksik! Lütfen 'Settings' (Ayarlar) panelinden geçerli bir "
                "NVIDIA API Key girin veya backend'i NVIDIA_API_KEY çevre değişkeniyle başlatın."
            )

        res = pipeline.run_pipeline(
            job_id=job_id,
            excel_file_path=file_path,
            natural_query=natural_query,
            previous_sql=job.get("previous_sql"),
            dialect=dialect,
            api_key=api_key,
            log_callback=log_callback,
            request_id=request_id
        )

        # İşin iptal edilip edilmediğini kontrol et
        current_job = get_job(job_id)
        if current_job and current_job["status"] == "cancelled":
            return

        if res["success"]:
            log_callback("SQL üretimi başarıyla tamamlandı.", 5)
            update_job_status(job_id, "completed", result_sql=res["generated_sql"])
        else:
            log_callback(f"SQL üretimi başarısız oldu: {res['error'] or 'Bilinmeyen hata'}", 5)
            # error_code sınırda ham string olarak taşınır (API sözleşmesi
            # tipsiz string kod taşır, enum değil). ErrorCode enum üyelerinden
            # .value çıkar; ham string ise olduğu gibi geç (defensive).
            ec = res.get("error_code")
            # Sprint 32.5: the worker may retry / dead-letter instead (inline: no hook).
            if on_failure is not None and on_failure(
                res["error"] or "SQL üretimi başarısız.", getattr(ec, "value", ec), is_transient_failure(res)
            ):
                return
            update_job_status(
                job_id, "failed",
                error_message=res["error"] or "SQL üretimi başarısız.",
                error_code=getattr(ec, "value", ec),
            )

    except Exception as e:
        # İptal edilmişse hata olarak kaydetme
        current_job = get_job(job_id)
        if current_job and current_job["status"] == "cancelled":
            return
        log_callback(f"Beklenmeyen hata: {str(e)}", 5)
        # error_code bilinçli olarak GEÇİLMEZ → NULL kalır. Registry'nin
        # INTERNAL → kod-yok tasarımıyla tutarlı: beklenmeyen bir job-runner
        # exception'ının taksonomi kodu yoktur.
        update_job_status(job_id, "failed", error_message=str(e))
