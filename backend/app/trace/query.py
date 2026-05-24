from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TraceQuery:
    limit: int = 50
    offset: int = 0
    sql_valid: Optional[bool] = None
    error_type: Optional[str] = None
    job_id: Optional[str] = None
    dialect: Optional[str] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None
