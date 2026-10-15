"""Where the persistent state lives (Sprint 32.8). One place, so backup/restore and the app agree."""
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def app_db_path() -> str:
    from app.database import get_db_path

    return get_db_path()


def trace_db_path() -> str:
    from app.trace.dependencies import get_trace_db_path

    return get_trace_db_path()


def upload_dir() -> str:
    from app.settings import get_settings

    configured = get_settings().upload_dir
    return os.path.abspath(configured) if configured else os.path.join(_BACKEND_DIR, "uploads")


def qdrant_dir() -> str:
    # Mirrors app/rag_manager.py (embedded Qdrant store next to the `app` package).
    return os.path.join(_BACKEND_DIR, "qdrant_data")


def backup_dir() -> str:
    from app.settings import get_settings

    configured = get_settings().backup_dir
    return os.path.abspath(configured) if configured else os.path.join(_BACKEND_DIR, "backups")
