from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, Dict, Any, List, Literal
from enum import Enum

from app.feedback import FeedbackVerdict, FeedbackCategory


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
    error_code: Optional[str] = None
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


# Sprint 27.3 - Feedback capture schemas
class FeedbackSubmitRequest(BaseModel):
    verdict: FeedbackVerdict
    category: Optional[FeedbackCategory] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    corrected_sql: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _check_invariants(self):
        # (2) doğru SQL'in hata kategorisi/düzeltmesi olmaz.
        if self.verdict == FeedbackVerdict.CORRECT:
            if self.category is not None or self.corrected_sql is not None:
                raise ValueError(
                    "verdict=correct ile category/corrected_sql verilemez"
                )
        # (3) 'other' serbest-metin gerekçe ister; aksi halde 27.9 için ölü sinyal.
        if self.category == FeedbackCategory.OTHER and not (
            self.note and self.note.strip()
        ):
            raise ValueError("category=other için note zorunludur")
        return self


class FeedbackDetailResponse(BaseModel):
    id: str
    job_id: str
    verdict: str
    category: Optional[str] = None
    note: Optional[str] = None
    corrected_sql: Optional[str] = None
    created_at: str


class FeedbackEnvelopeResponse(BaseModel):
    status: Literal["success"]
    feedback: FeedbackDetailResponse


# Sprint 27.4 - Query replay schemas (alanlar PLAIN str; enum sinir gecmez)
class ReplayRetrievalDelta(BaseModel):
    applicable: bool
    baseline_tables: List[str]
    observed_tables: List[str]
    added: List[str]
    removed: List[str]
    changed: bool


class ReplayValidationDelta(BaseModel):
    applicable: bool
    baseline_valid: Optional[bool] = None
    observed_valid: Optional[bool] = None
    baseline_issue_types: List[str]
    observed_issue_types: List[str]
    changed: bool


class ReplaySecurityDelta(BaseModel):
    applicable: bool
    baseline_denied: List[str]
    observed_denied: List[str]
    changed: bool


class ReplayDetailResponse(BaseModel):
    version: str
    job_id: str
    verdict: str
    baseline_trace_id: Optional[str] = None
    retrieval: Optional[ReplayRetrievalDelta] = None
    validation: Optional[ReplayValidationDelta] = None
    security: Optional[ReplaySecurityDelta] = None
    error_code: Optional[str] = None
    notes: List[str] = []


class ReplayEnvelopeResponse(BaseModel):
    status: Literal["success"]
    replay: ReplayDetailResponse


# Sprint 27.5 - Debug bundle schemas (alanlar PLAIN str/dict; enum sinir gecmez)
class BundleJobInfoResponse(BaseModel):
    status: Optional[str] = None
    dialect: Optional[str] = None
    error_code: Optional[str] = None
    has_natural_query: bool = False
    has_excel_input: bool = False
    result_sql_present: bool = False


class BundleSqlInfoResponse(BaseModel):
    generated_sql: Optional[str] = None
    last_generated_sql: Optional[str] = None
    sql_valid: Optional[bool] = None
    attempts: List[Any] = []
    sql_validation_errors: List[Any] = []


class BundleSchemaInfoResponse(BaseModel):
    selected_tables: List[str] = []
    schema_hash: Optional[str] = None
    table_count: int = 0


class BundleMetaResponse(BaseModel):
    bundle_contract_version: str
    replay_contract_version: Optional[str] = None
    trace_contract_version: Optional[str] = None
    dialect: Optional[str] = None


class BundleDetailResponse(BaseModel):
    version: str
    job_id: str
    job: BundleJobInfoResponse
    trace: Optional[dict] = None
    sql: Optional[BundleSqlInfoResponse] = None
    replay: Optional[dict] = None
    schema_: Optional[BundleSchemaInfoResponse] = Field(default=None, alias="schema")
    meta: Optional[BundleMetaResponse] = None

    model_config = {"populate_by_name": True}


class BundleEnvelopeResponse(BaseModel):
    status: Literal["success"]
    bundle: BundleDetailResponse


# Sprint 27.6 - Metrics contract schemas (alanlar PLAIN dict/str; enum sinir gecmez)
class MetricsWindowResponse(BaseModel):
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    dialect: Optional[str] = None
    trace_count: int
    truncated: bool
    scan_cap: int


class MetricsOutcomeResponse(BaseModel):
    total: int
    terminal_status: dict
    success_rate: Optional[float] = None


class MetricsErrorsResponse(BaseModel):
    by_code: dict
    by_category: dict


class MetricsLatencyResponse(BaseModel):
    count: int
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None


class MetricsDetailResponse(BaseModel):
    version: str
    window: MetricsWindowResponse
    outcome: MetricsOutcomeResponse
    errors: MetricsErrorsResponse
    latency_ms: MetricsLatencyResponse
    stages: dict


class MetricsEnvelopeResponse(BaseModel):
    status: Literal["success"]
    metrics: MetricsDetailResponse


# Sprint 27.7 - Admin dashboard schemas (alanlar PLAIN dict/str; enum sinir gecmez)
class DashboardWindowResponse(BaseModel):
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    dialect: Optional[str] = None
    trace_count: int
    truncated: bool
    scan_cap: int
    bucket: str
    timeseries_truncated: bool


class TimeseriesBucketResponse(BaseModel):
    bucket_start: str
    total: int
    success_rate: Optional[float] = None
    error_count: int
    p95_ms: Optional[float] = None


class TopErrorResponse(BaseModel):
    code: str
    category: str
    count: int


class FeedbackSummaryResponse(BaseModel):
    total: int
    by_verdict: dict
    by_category: dict


class RecentTraceResponse(BaseModel):
    job_id: Optional[str] = None
    trace_id: Optional[str] = None
    terminal_status: Optional[str] = None
    dialect: Optional[str] = None
    total_duration_ms: Optional[float] = None
    created_at: Optional[str] = None


class DashboardDetailResponse(BaseModel):
    version: str
    window: DashboardWindowResponse
    metrics: dict
    timeseries: List[TimeseriesBucketResponse]
    top_errors: List[TopErrorResponse]
    feedback: FeedbackSummaryResponse
    recent_activity: List[RecentTraceResponse]


class DashboardEnvelopeResponse(BaseModel):
    status: Literal["success"]
    dashboard: DashboardDetailResponse


# Sprint 27.8 - LLM usage/cost schemas (alanlar PLAIN dict/str/float; enum sinir gecmez)
class UsageWindowResponse(BaseModel):
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    bucket: str
    trace_count: int
    generation_count: int
    truncated: bool
    scan_cap: int
    timeseries_truncated: bool


class UsageTotalsResponse(BaseModel):
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float] = None
    unpriced_request_count: int


class ModelUsageResponse(BaseModel):
    # model_id, Pydantic v2'nin 'model_' korumali ad-alaniyla cakisir; kapatilir.
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float] = None


class ProviderUsageResponse(BaseModel):
    provider_id: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float] = None


class LatencyStatsResponse(BaseModel):
    count: int
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None


class UsageBucketResponse(BaseModel):
    bucket_start: str
    request_count: int
    total_tokens: int
    estimated_cost: Optional[float] = None


class PricingInfoResponse(BaseModel):
    models_priced: List[str]
    models_missing_price: List[str]


class LLMUsageDetailResponse(BaseModel):
    version: str
    currency: str
    window: UsageWindowResponse
    totals: UsageTotalsResponse
    by_model: List[ModelUsageResponse]
    by_provider: List[ProviderUsageResponse]
    latency_ms: LatencyStatsResponse
    finish_reasons: dict
    timeseries: List[UsageBucketResponse]
    pricing: PricingInfoResponse


class LLMUsageEnvelopeResponse(BaseModel):
    status: Literal["success"]
    usage: LLMUsageDetailResponse


# Sprint 27.9 - Feedback -> rule suggestion schemas (alanlar PLAIN str/list/dict/int)
class SuggestionWindowResponse(BaseModel):
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    feedback_count: int
    eligible_count: int
    suggestion_count: int
    truncated: bool
    scan_cap: int


class RuleSuggestionResponse(BaseModel):
    natural_query: str
    suggested_sql: str
    kind: str
    categories: List[str]
    support_count: int
    feedback_ids: List[str]
    job_ids: List[str]


class IneligibleResponse(BaseModel):
    total: int
    reasons: dict


class RuleSuggestionsDetailResponse(BaseModel):
    version: str
    window: SuggestionWindowResponse
    suggestions: List[RuleSuggestionResponse]
    by_kind: dict
    by_category: dict
    ineligible: IneligibleResponse


class RuleSuggestionsEnvelopeResponse(BaseModel):
    status: Literal["success"]
    suggestions: RuleSuggestionsDetailResponse


# Sprint 28.7 - Schema drift / sync
class StructuralDriftResponse(BaseModel):
    added_tables: List[str]
    removed_tables: List[str]
    added_columns: List[dict]
    removed_columns: List[dict]
    changed_columns: List[dict]
    added_fks: List[dict]
    removed_fks: List[dict]


class SchemaDriftEnvelopeResponse(BaseModel):
    status: Literal["success"]
    drifted: bool
    signature_version: str
    cached_signature: Optional[str] = None
    current_signature: str
    drift: StructuralDriftResponse


class SchemaSyncEnvelopeResponse(BaseModel):
    status: Literal["success"]
    action: Literal["rebuilt", "up_to_date"]
    drifted: bool
    signature_version: str
    cached_signature: Optional[str] = None
    current_signature: str
    drift: StructuralDriftResponse


# Sprint 28.8 - Embedding re-index
class ReindexStatusEnvelopeResponse(BaseModel):
    status: Literal["success"]
    model: str
    fresh: int
    stale: List[str]
    new: List[str]
    to_delete: List[str]
    orphaned_qdrant: List[str]


class ReindexEnvelopeResponse(BaseModel):
    status: Literal["success"]
    embedded: List[str]
    kept: int
    deleted: List[str]
    pruned: List[str]
    model: str
