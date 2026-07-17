import re
from typing import Any, Set

from app.errors import ErrorCode

def redact_sensitive_text(value: str, known_secrets: Set[str] = None) -> str:
    if not value or not isinstance(value, str):
        return value

    # 1. Redact general regex patterns
    # For patterns with capture groups (like api_key=value, password=value)
    prefix_patterns = [
        r"(?i)(api[_-]?key\s*=\s*)[^\s,;']+",
        r"(?i)(token\s*=\s*)[^\s,;']+",
        r"(?i)(password\s*=\s*)[^\s,;']+",
        r"(?i)(secret\s*=\s*)[^\s,;']+",
    ]
    for pattern in prefix_patterns:
        value = re.sub(pattern, r"\1[REDACTED]", value)

    # For patterns without capture groups (like sk-..., nvapi-...)
    simple_patterns = [
        r"sk-[A-Za-z0-9._-]+",
        r"nvapi-[A-Za-z0-9._-]+",
    ]
    for pattern in simple_patterns:
        value = re.sub(pattern, "[REDACTED]", value)

    # 2. Redact specific known secrets
    if known_secrets:
        for secret in known_secrets:
            if secret and len(secret) > 3:  # avoid redacting extremely short/empty strings
                escaped = re.escape(secret)
                value = re.sub(escaped, "[REDACTED]", value)

    return value

def redact_sensitive(value: Any, known_secrets: Set[str] = None) -> Any:
    # ErrorCode kapalı bir sözlüktür: asla kullanıcı verisi ya da secret
    # taşımaz. str alt sınıfı olduğu için aşağıdaki isinstance(value, str)
    # dalına düşer ve düz string'e indirgenirdi — tipi koruyoruz (Sprint 27.2).
    if isinstance(value, ErrorCode):
        return value
    if isinstance(value, str):
        return redact_sensitive_text(value, known_secrets)
    if isinstance(value, list):
        return [redact_sensitive(v, known_secrets) for v in value]
    if isinstance(value, dict):
        return {k: redact_sensitive(v, known_secrets) for k, v in value.items()}
    return value
