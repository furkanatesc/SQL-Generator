import sqlite3
import os
from typing import Optional, Dict, Any, List

def get_db_path():
    return os.getenv(
        "SQLGEN_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sqlgen.db")
    )

def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Configs tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configs (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Jobs tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                file_path TEXT,
                natural_query TEXT,
                previous_sql TEXT,
                result_sql TEXT,
                error_message TEXT,
                error_code TEXT,
                dialect TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Backward compatibility for existing jobs table
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN dialect TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN previous_sql TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN error_code TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists


        # Synonym Rules tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS synonym_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term TEXT NOT NULL,
                normalized_term TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_name TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.8,
                source TEXT NOT NULL DEFAULT 'manual',
                priority INTEGER NOT NULL DEFAULT 100,
                enabled INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Trace Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_traces (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                natural_query TEXT,
                candidate_tables TEXT,
                selected_tables TEXT,
                estimated_tokens INTEGER,
                generated_sql TEXT,
                sql_valid INTEGER,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Feedback Tablosu (Sprint 27.3 — append-only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                category TEXT,
                note TEXT,
                corrected_sql TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_job_id ON feedback (job_id)"
        )

        # Varsayılan bazı ayarları yerleştirelim (eğer yoksa)
        cursor.execute("INSERT OR IGNORE INTO configs (key, value) VALUES ('api_key', 'sqlgen_secret_dev_key')")
        cursor.execute("INSERT OR IGNORE INTO configs (key, value) VALUES ('llm_model', 'llama-3.3-nemotron-super-49b-v1.5')")
        cursor.execute("INSERT OR IGNORE INTO configs (key, value) VALUES ('vector_db', 'qdrant')")
        
        # Bootstrap Synonym / Ignore Kuralları
        cursor.execute("SELECT COUNT(*) as cnt FROM synonym_rules")
        if cursor.fetchone()["cnt"] == 0:
            bootstrap_rules = [
                ('hekim', 'hekim', 'concept', 'doktor', 0.95, 'manual', 10),
                ('doktor', 'doktor', 'concept', 'doktor', 0.95, 'manual', 10),
                ('dr', 'dr', 'concept', 'doktor', 0.90, 'manual', 20),
                ('branş', 'brans', 'concept', 'brans', 0.90, 'manual', 10),
                ('uzmanlık', 'uzmanlik', 'concept', 'brans', 0.85, 'manual', 20),
                ('hasta', 'hasta', 'concept', 'hasta', 0.95, 'manual', 10),
                ('ver', 'ver', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
                ('getir', 'getir', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
                ('listele', 'listele', 'ignore', 'ignore:command_verb', 1.00, 'manual', 1),
                ('bana', 'bana', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('olan', 'olan', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('ile', 'ile', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('ve', 've', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('veya', 'veya', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('için', 'icin', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('tum', 'tum', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('tüm', 'tum', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('sorgu', 'sorgu', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('sorguyu', 'sorguyu', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('tablo', 'tablo', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('kayıt', 'kayit', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('bilgi', 'bilgi', 'ignore', 'ignore:stopword', 1.00, 'manual', 1),
                ('sayısı', 'sayisi', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
                ('sayisi', 'sayisi', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
                ('toplam', 'toplam', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
                ('ortalama', 'ortalama', 'ignore', 'ignore:agg_intent', 1.00, 'manual', 1),
            ]
            cursor.executemany(
                "INSERT INTO synonym_rules (term, normalized_term, target_type, target_name, confidence, source, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
                bootstrap_rules
            )
        
        conn.commit()

# Config Helper Fonksiyonları
def get_config(key: str) -> Optional[str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM configs WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

def set_config(key: str, value: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configs (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

# Job Helper Fonksiyonları
def create_job(job_id: str, file_path: Optional[str] = None, natural_query: Optional[str] = None, previous_sql: Optional[str] = None, dialect: str = "postgres") -> Dict[str, Any]:
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (id, status, file_path, natural_query, previous_sql, dialect, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, "pending", file_path, natural_query, previous_sql, dialect, now, now)
        )
        conn.commit()
    return get_job(job_id)

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

# update_job_status'un yazabileceği kolonlar. SET cümlesi bu sabit
# whitelist'ten kurulur; kullanıcı girdisi kolon adına asla dönüşmez.
_UPDATABLE_JOB_COLUMNS = ("result_sql", "error_message", "error_code")

def update_job_status(
    job_id: str,
    status: str,
    result_sql: Optional[str] = None,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Job durumunu günceller. None geçilen alanlar DEĞİŞTİRİLMEZ.

    SET cümlesi non-None alanlardan dinamik kurulur; kolon adları
    _UPDATABLE_JOB_COLUMNS whitelist'inden gelir (SQL injection yüzeyi yok).
    """
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    provided = {
        "result_sql": result_sql,
        "error_message": error_message,
        "error_code": error_code,
    }
    fields = ["status = ?"]
    values: List[Any] = [status]
    for col in _UPDATABLE_JOB_COLUMNS:
        if provided[col] is not None:
            fields.append(f"{col} = ?")
            values.append(provided[col])
    fields.append("updated_at = ?")
    values.append(now)
    values.append(job_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?",
            values
        )
        conn.commit()
    return get_job(job_id)

ALLOWED_JOB_SORT_COLUMNS = {"created_at", "updated_at"}
ALLOWED_SORT_ORDERS = {"asc", "desc"}

def list_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> List[Dict[str, Any]]:
    if sort_by not in ALLOWED_JOB_SORT_COLUMNS:
        raise ValueError("Invalid sort_by")
    if sort_order not in ALLOWED_SORT_ORDERS:
        raise ValueError("Invalid sort_order")

    order_clause = f"{sort_by} {sort_order.upper()}"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                f"SELECT * FROM jobs WHERE status = ? ORDER BY {order_clause} LIMIT ? OFFSET ?",
                (status, limit, offset)
            )
        else:
            cursor.execute(
                f"SELECT * FROM jobs ORDER BY {order_clause} LIMIT ? OFFSET ?",
                (limit, offset)
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

# Feedback Helper Fonksiyonları (Sprint 27.3 — append-only)
def create_feedback(
    feedback_id: str,
    job_id: str,
    verdict: str,
    category: Optional[str] = None,
    note: Optional[str] = None,
    corrected_sql: Optional[str] = None,
) -> Dict[str, Any]:
    """feedback tablosuna append-only bir satır ekler ve döndürür.

    Enum değerleri sınırda (Pydantic) doğrulanmış PLAIN STRING olarak gelir;
    bu fonksiyon ince persister'dır ve app.feedback taksonomisini import ETMEZ.
    """
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO feedback
                (id, job_id, verdict, category, note, corrected_sql, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (feedback_id, job_id, verdict, category, note, corrected_sql, now),
        )
        conn.commit()
    return get_feedback(feedback_id)


def get_feedback(feedback_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_feedback_for_job(job_id: str) -> List[Dict[str, Any]]:
    """Bir job'ın tüm feedback'ini kronolojik döndürür.

    27.9 tüketicisi bir job'ın tüm sinyal geçmişini bu fonksiyonla okur.
    Sıralama: created_at ASC, sonra rowid ASC. rowid tiebreak, aynı
    created_at (coarse clock) durumunda insertion-order'ı deterministik kılar
    — aksi halde eş-zaman-damgalı satırların sırası tanımsız kalırdı.
    Bilinmeyen job_id → boş liste (patlamaz).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM feedback WHERE job_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (job_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
