"""Shared, dialect-generic SQL text utilities for the security contracts.

Internal to ``app.security`` (note the leading underscore): a tiny, dependency-free
lexer/normalizer reused by the read-only enforcement contract (26.2) and the query
risk classifier (26.3) so they classify the *same* view of a statement — executable
code only, with comments and string/identifier literals removed. No SQL parser
dependency, no I/O.

The single source of truth for "what part of this SQL is executable code":

* :func:`sanitize` removes comments and masks string literals / quoted identifiers.
* :func:`normalize` collapses whitespace.
* :func:`to_executable_core` does both and strips one optional trailing semicolon.
* :func:`leading_keyword` returns the statement's leading keyword (literal-free).
"""

import re
from typing import Optional

# Number of leading-keyword characters echoed for audit. Deliberately the leading
# SQL keyword only (e.g. SELECT / WITH / DROP) — never query content — so no string
# literal, value, or PII can leak through a result that stores it.
PREFIX_MAX_LEN = 32

_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_TOKEN_RE = re.compile(r"^\s*([A-Za-z_]+)")


def sanitize(sql: str) -> str:
    """Return executable code only: comments removed, string literals and
    double-quoted identifiers replaced by a single-space placeholder.

    A small dialect-generic lexer. Single quotes (``'``) delimit string literals,
    double quotes (``"``) delimit identifiers; a doubled quote (``''`` / ``""``)
    is an embedded quote, not a terminator (ANSI / standard_conforming_strings).
    ``--`` runs to end of line, ``/* ... */`` is a (non-nested) block comment.

    Errs toward safety: an unterminated literal/comment is masked to end of input
    (its tail cannot be executable code anyway), and a non-nested ``*/`` scan that
    closes "early" only leaves MORE text as code — conservative, never a bypass.
    """
    out = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c == "'" or c == '"':
            quote = c
            i += 1
            while i < n:
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # doubled = escaped quote
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        elif c == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] not in "\r\n":
                i += 1
            out.append(" ")
        elif c == "/" and nxt == "*":
            i += 2
            while i < n and not (sql[i] == "*" and i + 1 < n and sql[i + 1] == "/"):
                i += 1
            i += 2  # consume the closing */ (no-op past end if unterminated)
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def normalize(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip. Deterministic."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def to_executable_core(sql: str) -> str:
    """``sanitize`` -> ``normalize`` -> strip one optional trailing semicolon.

    The canonical "executable core" that classifiers scan: a single normalized line
    of code with comments/literals removed and at most one trailing ``;`` dropped
    (any remaining ``;`` therefore signals a genuine multi-statement).
    """
    norm = normalize(sanitize(sql))
    return norm[:-1].strip() if norm.endswith(";") else norm


def leading_keyword(core: str, max_len: int = PREFIX_MAX_LEN) -> Optional[str]:
    """Return the upper-cased leading keyword of an executable core, or ``None``.

    Literal-free by construction (it is only the leading identifier token), so it is
    safe to store in an audit result without leaking query content.
    """
    match = _LEADING_TOKEN_RE.match(core)
    if not match:
        return None
    return match.group(1).upper()[:max_len]
