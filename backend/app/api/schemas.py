from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Literal
from enum import Enum


class RuntimeConfigDiagnostics(BaseModel):
    environment: str
    debug_endpoints_enabled: bool
    cors_origins_count: int
    upload_dir_configured: bool
    api_key_configured: bool
    startup_warnings_count: int
    startup_critical_warnings_count: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    database: str
    config: RuntimeConfigDiagnostics


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unhealthy"]
    database_reachable: bool
    api_key_configured: bool
    upload_dir_writable: bool
    critical_warnings_count: int


class ConfigUpdateRequest(BaseModel):
    value: str


class ConfigResponse(BaseModel):
    key: str
    value: str


class ConfigUpdateResponse(BaseModel):
    status: Literal["success"]
    key: str
    value: str


class JobCreateRequest(BaseModel):
    natural_query: str
    previous_sql: Optional[str] = None


class JobDetailResponse(BaseModel):
    id: str
    status: str
    file_path: Optional[str] = None
    natural_query: Optional[str] = None
    previous_sql: Optional[str] = None
    result_sql: Optional[str] = None
    error_message: Optional[str] = None
    dialect: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobEnvelopeResponse(BaseModel):
    status: Literal["success"]
    job: JobDetailResponse


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobSortBy(str, Enum):
    created_at = "created_at"
    updated_at = "updated_at"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class JobsListResponse(BaseModel):
    jobs: List[JobDetailResponse]
    limit: int
    offset: int
    count: int
    status: Optional[JobStatus]
    sort_by: JobSortBy
    sort_order: SortOrder


class CancelJobResponse(BaseModel):
    status: Literal["success"]
    message: str
    job: JobDetailResponse


class FileUploadResponse(BaseModel):
    status: Literal["success"]
    message: str
    job: JobDetailResponse


# Additional schemas from main.py moved for central organization
class RelationItem(BaseModel):
    source: str
    source_col: str
    target: str
    target_col: str


class CustomRelationsUpdate(BaseModel):
    relations: List[RelationItem]


class DisabledRelationsUpdate(BaseModel):
    relations: List[RelationItem]


class SchemaFilterUpdate(BaseModel):
    hidden_tables: List[str]
    hidden_columns: Dict[str, List[str]]


class BusinessRuleIndexRequest(BaseModel):
    rule_id: str
    rule_text: str
    sql_mapping: str


class SQLHistoryIndexRequest(BaseModel):
    history_id: str
    natural_query: str
    sql: str


class RAGSearchRequest(BaseModel):
    query: str
    collection: str
    limit: Optional[int] = 3


# PR 11.2 - Error response schemas
class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorBody
