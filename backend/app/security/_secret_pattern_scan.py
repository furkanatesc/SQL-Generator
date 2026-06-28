"""Shared raw-secret pattern detector for reference-only string fields.

Single source of truth for the heuristics historically inlined in
``SQLConnectionSecretRef.__post_init__`` (26.x connection abstraction). Pure,
deterministic, secret-free: returns matched MARKER NAMES only, never the
surrounding value. Used both to validate connection refs and by the 26.10
credential-vault leak-guard.
"""

from typing import Tuple

SECRET_ASSIGNMENT_PATTERNS: Tuple[str, ...] = (
    "password=",
    "token=",
    "secret=",
    "key=",
)
CONNECTION_STRING_MARKER = "://"


def scan_secret_patterns(value: str) -> Tuple[str, ...]:
    """Return raw-secret marker names found in a reference-only string.

    Detects a connection-string marker (``://``) and credential assignment
    patterns (``password=`` / ``token=`` / ``secret=`` / ``key=``,
    case-insensitive). Returns the matched marker names only — never the
    offending substring. Empty tuple means clean.
    """
    if not isinstance(value, str):
        raise TypeError("scan_secret_patterns expects a str")
    found = []
    if CONNECTION_STRING_MARKER in value:
        found.append(CONNECTION_STRING_MARKER)
    lowered = value.lower()
    for pattern in SECRET_ASSIGNMENT_PATTERNS:
        if pattern in lowered:
            found.append(pattern)
    return tuple(found)
