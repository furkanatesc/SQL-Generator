from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Literal


# PR 11.1 - Core API schemas
class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    database: str


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


class JobEnvelopeResponse(BaseModel):
    status: Literal["success"]
    job: Dict[str, Any]


class JobsListResponse(BaseModel):
    jobs: List[Dict[str, Any]]


class CancelJobResponse(BaseModel):
    status: Literal["success"]
    message: str
    job: Dict[str, Any]


class FileUploadResponse(BaseModel):
    status: Literal["success"]
    message: str
    job: Dict[str, Any]


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
