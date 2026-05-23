import uuid
import json
import logging
from typing import Dict, Any, List, Optional
from app.database import get_db_connection

logger = logging.getLogger("trace_store")

class TraceStore:
    """
    Sistemin her adımını (hangi tablolar aday oldu, hangileri seçildi, token ne kadardı, vb.)
    veritabanına kaydeden ve okuyan bileşen. v1 observability'sinin temelidir.
    """
    def __init__(self):
        pass

    def save_trace(self, job_id: str, natural_query: str, candidate_tables: List[Dict[str, Any]], 
                   selected_tables: List[str], estimated_tokens: int, generated_sql: str, 
                   sql_valid: bool, error_message: Optional[str]) -> str:
        trace_id = str(uuid.uuid4())
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO query_traces (
                        id, job_id, natural_query, candidate_tables, selected_tables, 
                        estimated_tokens, generated_sql, sql_valid, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_id,
                        job_id,
                        natural_query,
                        json.dumps(candidate_tables, ensure_ascii=False),
                        json.dumps(selected_tables, ensure_ascii=False),
                        estimated_tokens,
                        generated_sql,
                        1 if sql_valid else 0,
                        error_message or ""
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save trace for job {job_id}: {e}")
        return trace_id

    def get_traces(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        traces = []
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, job_id, natural_query, candidate_tables, selected_tables, 
                           estimated_tokens, generated_sql, sql_valid, error_message, created_at
                    FROM query_traces
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset)
                )
                for row in cursor.fetchall():
                    trace = dict(row)
                    # Parse JSON fields
                    try:
                        trace["candidate_tables"] = json.loads(trace["candidate_tables"])
                    except:
                        trace["candidate_tables"] = []
                        
                    try:
                        trace["selected_tables"] = json.loads(trace["selected_tables"])
                    except:
                        trace["selected_tables"] = []
                        
                    trace["sql_valid"] = bool(trace["sql_valid"])
                    traces.append(trace)
        except Exception as e:
            logger.error(f"Failed to get traces: {e}")
        return traces
