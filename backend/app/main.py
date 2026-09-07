import os
import logging
import uuid
import datetime
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks, status, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import (
    init_db, get_job, create_job, update_job_status, list_jobs, get_config, set_config
)
from app.auth import verify_api_key
from app.api.debug_traces import router as debug_traces_router
from app.api.feedback import router as feedback_router
from app.api.debug_replay import router as debug_replay_router
from app.api.debug_bundle_api import router as debug_bundle_router
from app.api.metrics_api import router as metrics_router
from app.api.dashboard_api import router as dashboard_router
from app.api.llm_usage_api import router as llm_usage_router
from app.api.rule_suggestions_api import router as rule_suggestions_router
from app.api.schema_sync_api import router as schema_sync_router
from app.api.cache_api import router as cache_router
from app.api.v1_meta import router as v1_meta_router
from app.api.workspaces import router as workspaces_router
from app.api.connections import router as connections_router
from fastapi.exceptions import RequestValidationError
from app.settings import get_settings
from app.api.errors import http_exception_handler, validation_exception_handler, unhandled_exception_handler
from app.middleware.request_logging import RequestLoggingMiddleware
from app.health import build_health_response, check_readiness
from app.api.schemas import (
    HealthResponse,
    ReadinessResponse,
    ConfigUpdateRequest,
    ConfigResponse,
    ConfigUpdateResponse,
    JobCreateRequest,
    JobDetailResponse,
    JobEnvelopeResponse,
    JobsListResponse,
    JobStatus,
    JobSortBy,
    SortOrder,
    CancelJobResponse,
    FileUploadResponse,
    ErrorResponse,
    RelationItem,
    CustomRelationsUpdate,
    DisabledRelationsUpdate,
    SchemaFilterUpdate,
    BusinessRuleIndexRequest,
    SQLHistoryIndexRequest,
    RAGSearchRequest,
)

# Global thread-safe logs ve stream yapıları
import queue
import asyncio
import json
from fastapi.responses import StreamingResponse

# format: {job_id: [{"message": str, "step": int, "timestamp": str}]}
job_logs_cache = {}
# format: {job_id: [queue.Queue]}
job_queues = {}

settings = get_settings()

# Uploads klasörünü oluştur
if settings.upload_dir:
    UPLOAD_DIR = os.path.abspath(settings.upload_dir)
else:
    UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# FastAPI uygulaması
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(debug_traces_router)
app.include_router(feedback_router)
app.include_router(debug_replay_router)
app.include_router(debug_bundle_router)
app.include_router(metrics_router)
app.include_router(dashboard_router)
app.include_router(llm_usage_router)
app.include_router(rule_suggestions_router)
app.include_router(schema_sync_router)
app.include_router(cache_router)
app.include_router(v1_meta_router)
app.include_router(workspaces_router)
app.include_router(connections_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Request Logging (outer-most to trace all incoming requests)
app.add_middleware(RequestLoggingMiddleware)

# Startup
rag_manager = None
logger = logging.getLogger("app.main")

@app.on_event("startup")
def startup_event():
    global rag_manager
    init_db()
    
    # Run startup validation checks
    try:
        from app.startup_validation import validate_runtime_config
        val_result = validate_runtime_config()
        for w in val_result.warnings:
            logger.warning(
                "startup_config_warning code=%s severity=%s message=%s",
                w.code, w.severity, w.message
            )
    except Exception as e:
        logger.error("Failed to run startup validation: %s", str(e))
        
    try:
        from app.rag_manager import RAGManager
        rag_manager = RAGManager()
        print("RAG Manager initialized successfully.")
    except Exception as e:
        print(f"RAG Manager initialization failed: {e}")

# API test endpoint'i
@app.get("/health", response_model=HealthResponse)
def health():
    return build_health_response()

@app.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}})
def readiness(response: Response):
    diagnostics = check_readiness()
    
    is_ready = (
        diagnostics["database_reachable"]
        and diagnostics["api_key_configured"]
        and diagnostics["upload_dir_writable"]
        and (diagnostics["critical_warnings_count"] == 0)
    )
    
    content = {
        "status": "ok" if is_ready else "unhealthy",
        "database_reachable": diagnostics["database_reachable"],
        "api_key_configured": diagnostics["api_key_configured"],
        "upload_dir_writable": diagnostics["upload_dir_writable"],
        "critical_warnings_count": diagnostics["critical_warnings_count"]
    }
    
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return content

# 1. Config API
@app.get("/api/configs/{key}", dependencies=[Depends(verify_api_key)], response_model=ConfigResponse, responses={404: {"model": ErrorResponse}})
def get_system_config(key: str):
    val = get_config(key)
    if val is None:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found.")
    return {"key": key, "value": val}

@app.post("/api/configs/{key}", dependencies=[Depends(verify_api_key)], response_model=ConfigUpdateResponse, responses={400: {"model": ErrorResponse}})
def set_system_config(key: str, data: ConfigUpdateRequest):
    set_config(key, data.value)
    return {"status": "success", "key": key, "value": data.value}

# 2. File Upload API
@app.post("/api/files/upload", dependencies=[Depends(verify_api_key)], response_model=FileUploadResponse, responses={400: {"model": ErrorResponse}})
def upload_excel_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    natural_query: Optional[str] = Form(None)
):
    # Dosya uzantı kontrolü
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".xlsx", ".xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only Excel files (.xlsx, .xls) are allowed."
        )
    
    # Eşsiz bir isimle kaydet
    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}{file_ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # SQLite üzerinde Job oluştur
    dialect = get_config("target_db_type") or "postgres"
    job = create_job(job_id=job_id, file_path=dest_path, natural_query=natural_query, dialect=dialect)
    
    # Arka planda gerçek SQL üretim pipeline'ını çalıştır
    background_tasks.add_task(process_job_pipeline, job_id, request_id=getattr(request.state, "request_id", None))
    
    return {
        "status": "success",
        "message": "File uploaded successfully. Job initiated.",
        "job": job
    }

# 3. Job API
@app.post("/api/jobs/without-file", dependencies=[Depends(verify_api_key)], response_model=JobEnvelopeResponse, responses={422: {"model": ErrorResponse}})
def start_job_without_file(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    http_request: Request
):
    if not request.natural_query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", "natural_query"], "msg": "natural_query cannot be empty or whitespace", "type": "value_error"}]
        )
        
    job_id = str(uuid.uuid4())
    dialect = get_config("target_db_type") or "postgres"
    job = create_job(job_id=job_id, natural_query=request.natural_query, previous_sql=request.previous_sql, dialect=dialect)
    background_tasks.add_task(process_job_pipeline, job_id, request_id=getattr(http_request.state, "request_id", None))
    return {
        "status": "success",
        "job": job
    }

@app.get("/api/jobs", dependencies=[Depends(verify_api_key)], response_model=JobsListResponse)
def get_jobs_list(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[JobStatus] = Query(default=None),
    sort_by: JobSortBy = Query(default=JobSortBy.created_at),
    sort_order: SortOrder = Query(default=SortOrder.desc),
):
    status_value = status.value if status else None
    sort_by_value = sort_by.value
    sort_order_value = sort_order.value

    jobs = list_jobs(
        limit=limit,
        offset=offset,
        status=status_value,
        sort_by=sort_by_value,
        sort_order=sort_order_value,
    )
    return {
        "jobs": jobs,
        "limit": limit,
        "offset": offset,
        "count": len(jobs),
        "status": status_value,
        "sort_by": sort_by_value,
        "sort_order": sort_order_value,
    }

@app.get("/api/jobs/{job_id}", dependencies=[Depends(verify_api_key)], response_model=JobDetailResponse, responses={404: {"model": ErrorResponse}})
def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    return job

# 3.1. Job SSE Log Stream API
@app.get("/api/jobs/{job_id}/stream", dependencies=[Depends(verify_api_key)])
async def stream_job_logs(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
        
    async def log_generator():
        # Önceden üretilmiş tüm logları istemciye sırayla bas
        if job_id in job_logs_cache:
            for log_entry in job_logs_cache[job_id]:
                yield f"data: {json.dumps(log_entry)}\n\n"
                
        # Eğer iş zaten tamamlanmış, hata almış veya iptal edilmişse akışı sonlandır
        current_job = get_job(job_id)
        if current_job and current_job["status"] in ["completed", "failed", "cancelled"]:
            return
            
        # Dinleyici için thread-safe bir Queue tanımla ve kaydet
        q = queue.Queue()
        if job_id not in job_queues:
            job_queues[job_id] = []
        job_queues[job_id].append(q)
        
        try:
            loop = asyncio.get_running_loop()
            while True:
                try:
                    # thread-safe kuyruktan asenkron olarak non-blocking oku
                    event = await loop.run_in_executor(None, q.get, True, 1.0)
                    if event == "EOF":
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Bağlantıyı canlı tutmak için ping gönder
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # İstemci ayrıldığında kuyruğu temizle
            if job_id in job_queues:
                if q in job_queues[job_id]:
                    job_queues[job_id].remove(q)
                if not job_queues[job_id]:
                    del job_queues[job_id]
                    
    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(verify_api_key)], response_model=CancelJobResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
def cancel_job_execution(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    
    if job["status"] in ["completed", "failed", "cancelled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in final state: '{job['status']}'."
        )
    
    updated_job = update_job_status(job_id, "cancelled")
    return {
        "status": "success",
        "message": "Job cancellation requested.",
        "job": updated_job
    }

# Gerçek Asenkron SQL Üretim Pipeline Worker'ı
def process_job_pipeline(job_id: str, request_id: Optional[str] = None):
    from app.sql_pipeline import SQLGenerationPipeline
    from app.database import get_job, update_job_status, get_config
    import datetime
    
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
        if job_id not in job_logs_cache:
            job_logs_cache[job_id] = []
        job_logs_cache[job_id].append(log_entry)
        
        if job_id in job_queues:
            for q in job_queues[job_id]:
                q.put(log_entry)
    
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
        import os
        if (not api_key or api_key == "sqlgen_secret_dev_key") and not os.environ.get("NVIDIA_API_KEY"):
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
    finally:
        # Tüm SSE dinleyicilerini kapatmak için EOF sinyali gönder
        if job_id in job_queues:
            for q in job_queues[job_id]:
                q.put("EOF")

# 4. Schema API
@app.get("/api/schema/raw", dependencies=[Depends(verify_api_key)])
def get_raw_schema(refresh: bool = Query(False, description="Zorla yenileme (DB'den ham şemayı tekrar çeker)")):
    """
    Veritabanından (veya cache'den) hiçbir filtre uygulanmamış HAM şemayı döndürür.
    Bu uç nokta, arayüzde (Settings) tabloları gizleme/gösterme amaçlı kullanılır.
    """
    from app.schema_manager import SchemaManager
    try:
        sm = SchemaManager()
        raw_schema = sm.get_raw_schema()
        return {"status": "success", "schema": raw_schema}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/schema", dependencies=[Depends(verify_api_key)])
def get_database_schema():
    from app.schema_manager import SchemaManager
    try:
        sm = SchemaManager()
        schema = sm.load_schema(force_refresh=False)
        return {"status": "success", "schema": schema}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Veritabanı şeması okunamadı: {str(e)}"
        )

@app.post("/api/schema/refresh", dependencies=[Depends(verify_api_key)])
def refresh_database_schema():
    from app.schema_manager import SchemaManager
    try:
        sm = SchemaManager()
        schema = sm.load_schema(force_refresh=True)
        return {
            "status": "success",
            "message": "Şema önbelleği başarıyla yenilendi.",
            "schema": schema
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Veritabanı bağlantısı veya şema yenileme başarısız oldu: {str(e)}"
        )

# Custom and Disabled Relations API
@app.get("/api/schema/custom-relations", dependencies=[Depends(verify_api_key)])
def get_custom_relations():
    from app.database import get_config
    db_type = get_config("target_db_type") or "sqlite"
    val = get_config(f"custom_relations_{db_type}") or "[]"
    try:
        return {"status": "success", "relations": json.loads(val)}
    except Exception:
        return {"status": "success", "relations": []}

@app.post("/api/schema/custom-relations", dependencies=[Depends(verify_api_key)])
def save_custom_relations(data: CustomRelationsUpdate):
    from app.database import set_config, get_config
    db_type = get_config("target_db_type") or "sqlite"
    relations_list = [r.dict() for r in data.relations]
    set_config(f"custom_relations_{db_type}", json.dumps(relations_list, ensure_ascii=False))
    return {"status": "success", "message": "Özel ilişkiler başarıyla kaydedildi."}

@app.get("/api/schema/disabled-relations", dependencies=[Depends(verify_api_key)])
def get_disabled_relations():
    from app.database import get_config
    db_type = get_config("target_db_type") or "sqlite"
    val = get_config(f"disabled_relations_{db_type}") or "[]"
    try:
        return {"status": "success", "relations": json.loads(val)}
    except Exception:
        return {"status": "success", "relations": []}

@app.post("/api/schema/disabled-relations", dependencies=[Depends(verify_api_key)])
def save_disabled_relations(data: DisabledRelationsUpdate):
    from app.database import set_config, get_config
    db_type = get_config("target_db_type") or "sqlite"
    relations_list = [r.dict() for r in data.relations]
    set_config(f"disabled_relations_{db_type}", json.dumps(relations_list, ensure_ascii=False))
    return {"status": "success", "message": "Devre dışı bırakılmış ilişkiler başarıyla kaydedildi."}

@app.get("/api/schema/filters", dependencies=[Depends(verify_api_key)])
def get_schema_filters():
    from app.database import get_config
    db_type = get_config("target_db_type") or "sqlite"
    hidden_tables = get_config(f"hidden_tables_{db_type}") or "[]"
    hidden_columns = get_config(f"hidden_columns_{db_type}") or "{}"
    try:
        return {
            "status": "success",
            "hidden_tables": json.loads(hidden_tables),
            "hidden_columns": json.loads(hidden_columns)
        }
    except Exception:
        return {"status": "success", "hidden_tables": [], "hidden_columns": {}}

@app.post("/api/schema/filters", dependencies=[Depends(verify_api_key)])
def save_schema_filters(data: SchemaFilterUpdate):
    from app.database import set_config, get_config
    db_type = get_config("target_db_type") or "sqlite"
    set_config(f"hidden_tables_{db_type}", json.dumps(data.hidden_tables, ensure_ascii=False))
    set_config(f"hidden_columns_{db_type}", json.dumps(data.hidden_columns, ensure_ascii=False))
    return {"status": "success", "message": "Şema filtreleri başarıyla kaydedildi."}

@app.get("/api/rag/stats", dependencies=[Depends(verify_api_key)])
def get_rag_stats():
    global rag_manager
    if not rag_manager:
        return {"status": "error", "message": "RAG has not been initialized."}
    
    try:
        stats = {}
        for col in ["schema_ddl", "business_rules", "sql_history"]:
            info = rag_manager.client.get_collection(collection_name=col)
            stats[col] = info.points_count
        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/api/rag/search", dependencies=[Depends(verify_api_key)])
def search_rag(req: RAGSearchRequest):
    global rag_manager
    if not rag_manager:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="RAG system is not initialized.")
    
    try:
        from app.database import get_config
        api_key = get_config("nvidia_api_key") or get_config("api_key")
        
        import os
        if (not api_key or api_key == "sqlgen_secret_dev_key") and not os.environ.get("NVIDIA_API_KEY"):
            raise ValueError("RAG Arama yapmak için geçerli bir NVIDIA API Key gereklidir.")

        if req.collection == "schema_ddl":
            results = rag_manager.search_ddl(req.query, limit=req.limit, api_key=api_key)
        elif req.collection == "business_rules":
            results = rag_manager.search_business_rules(req.query, limit=req.limit, api_key=api_key)
        elif req.collection == "sql_history":
            results = rag_manager.search_sql_history(req.query, limit=req.limit, api_key=api_key)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz RAG koleksiyon adı.")
            
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/api/rag/index/business-rule", dependencies=[Depends(verify_api_key)])
def index_business_rule(req: BusinessRuleIndexRequest):
    global rag_manager
    if not rag_manager:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="RAG system not initialized.")
    try:
        from app.database import get_config
        api_key = get_config("nvidia_api_key") or get_config("api_key")
        
        import os
        if (not api_key or api_key == "sqlgen_secret_dev_key") and not os.environ.get("NVIDIA_API_KEY"):
            raise ValueError("RAG İndeksleme yapmak için geçerli bir NVIDIA API Key gereklidir.")

        rag_manager.index_business_rule(
            rule_id=req.rule_id,
            rule_text=req.rule_text,
            sql_mapping=req.sql_mapping,
            api_key=api_key
        )
        return {"status": "success", "message": "Business rule indexed successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/api/rag/index/sql-history", dependencies=[Depends(verify_api_key)])
def index_sql_history(req: SQLHistoryIndexRequest):
    global rag_manager
    if not rag_manager:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="RAG system not initialized.")
    try:
        from app.database import get_config
        api_key = get_config("nvidia_api_key") or get_config("api_key")
        
        import os
        if (not api_key or api_key == "sqlgen_secret_dev_key") and not os.environ.get("NVIDIA_API_KEY"):
            raise ValueError("RAG İndeksleme yapmak için geçerli bir NVIDIA API Key gereklidir.")

        rag_manager.index_sql_history(
            history_id=req.history_id,
            natural_query=req.natural_query,
            sql=req.sql,
            api_key=api_key
        )
        return {"status": "success", "message": "SQL history pair indexed successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
