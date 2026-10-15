"""Central logging configuration (Sprint 32.9).

Before 32.9 the API process had no logging configuration: uvicorn only configures its own
`uvicorn.*` loggers, so `app.*` INFO records (e.g. the `http_request` events of
RequestLoggingMiddleware) fell through to Python's last-resort handler, which prints WARNING+
only. `configure_logging()` is called by the API (at import), the worker and the CLIs:

- level `NL2SQL_LOG_LEVEL`, format `NL2SQL_LOG_FORMAT` (`text` | `json`, one object per line);
- `request_id` / `job_id` context (contextvars) on every record;
- secret redaction (27.x patterns + known secret values) on messages and tracebacks, applied
  to a copy of each record in the formatter (other handlers see the original);
- uvicorn loggers routed to the same handler; `uvicorn.access` raised to WARNING because the
  request_id-carrying `http_request` event already logs every request.

Idempotent and polite: it only replaces the handler it installed itself, so other handlers
(e.g. pytest's caplog) are left alone.
"""
import contextvars
import datetime as dt
import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import IO, Iterator, Optional

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)

_HANDLER_MARK = "_sqlgen_handler"
_SECRETS_TTL_SECONDS = 60.0


@contextmanager
def log_context(request_id: Optional[str] = None, job_id: Optional[str] = None) -> Iterator[None]:
    tokens = []
    if request_id is not None:
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if job_id is not None:
        tokens.append((job_id_var, job_id_var.set(job_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.job_id = job_id_var.get()
        return True


class Redactor:
    """Masks secrets in a *copy* of the record (message + traceback), so other handlers
    attached to the same logger (e.g. pytest's caplog) still see the original record."""

    def __init__(self):
        self._secrets: set = set()
        self._loaded_at = float("-inf")

    def _known_secrets(self) -> set:
        now = time.monotonic()
        if now - self._loaded_at > _SECRETS_TTL_SECONDS:
            try:
                from app.secret_resolver import known_secret_values

                self._secrets = {s for s in known_secret_values() if len(s) >= 6}
            except Exception:
                self._secrets = set()
            self._loaded_at = now
        return self._secrets

    @staticmethod
    def _redact_message(message: str, secrets: set) -> str:
        from app.trace.redaction import redact_sensitive, redact_sensitive_text

        # JSON event messages (http_request, ...) are redacted value by value: the text
        # patterns (e.g. `api_key=...`) would otherwise swallow the closing quote.
        if message.startswith("{"):
            try:
                event = json.loads(message)
            except ValueError:
                event = None
            if isinstance(event, dict):
                return json.dumps(redact_sensitive(event, secrets), ensure_ascii=False, default=str)
        return redact_sensitive_text(message, secrets)

    def redacted_copy(self, record: logging.LogRecord, formatter: logging.Formatter) -> logging.LogRecord:
        from app.trace.redaction import redact_sensitive_text

        secrets = self._known_secrets()
        copy = logging.makeLogRecord(record.__dict__)
        try:
            copy.msg = self._redact_message(record.getMessage(), secrets)
            copy.args = None
        except Exception:
            pass
        exc_text = record.exc_text
        if record.exc_info and not exc_text:
            exc_text = formatter.formatException(record.exc_info)
        copy.exc_info = None
        copy.exc_text = redact_sensitive_text(exc_text, secrets) if exc_text else None
        return copy


class JsonFormatter(logging.Formatter):
    def __init__(self, redactor: Optional[Redactor] = None):
        super().__init__()
        self.redactor = redactor or Redactor()

    def format(self, record: logging.LogRecord) -> str:
        record = self.redactor.redacted_copy(record, self)
        payload = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        merged = False
        if message.startswith("{"):
            try:
                event = json.loads(message)
                if isinstance(event, dict):
                    payload.update(event)
                    merged = True
            except ValueError:
                pass
        if not merged:
            payload["message"] = message
        for key in ("request_id", "job_id"):
            value = getattr(record, key, None)
            if value and key not in payload:
                payload[key] = value
        if record.exc_text:
            payload["exc_info"] = record.exc_text
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self, redactor: Optional[Redactor] = None):
        super().__init__("%(asctime)s %(levelname)s %(name)s%(ctx)s %(message)s")
        self.redactor = redactor or Redactor()

    def format(self, record: logging.LogRecord) -> str:
        record = self.redactor.redacted_copy(record, self)
        parts = []
        if getattr(record, "request_id", None):
            parts.append(f"req={record.request_id}")
        if getattr(record, "job_id", None):
            parts.append(f"job={record.job_id}")
        record.ctx = f" [{' '.join(parts)}]" if parts else ""
        return super().format(record)


def configure_logging(level: Optional[str] = None, fmt: Optional[str] = None,
                      stream: Optional[IO] = None) -> logging.Handler:
    """(Re)install SQLGen's root handler. Defaults come from Settings."""
    if level is None or fmt is None:
        from app.settings import get_settings

        settings = get_settings()
        level = level or settings.log_level
        fmt = fmt or settings.log_format

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARK, False):
            root.removeHandler(existing)

    handler = logging.StreamHandler(stream or sys.stderr)
    setattr(handler, _HANDLER_MARK, True)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [h for h in lg.handlers if getattr(h, _HANDLER_MARK, False)]
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = True
    access.setLevel(logging.WARNING)
    return handler
