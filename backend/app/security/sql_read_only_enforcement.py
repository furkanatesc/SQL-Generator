"""Sprint 26.2 — Read-Only Enforcement Hardening (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint pulls the notion of
"is this SQL read-only?" out of scattered, ad-hoc string checks and into a
single, deterministic, contract-first enforcement layer that the rest of the
system can share.

The Phase 7 security triangle, three distinct questions answered by three
distinct contracts:

* Permission policy (26.0) — *may this subject/context perform this action on
  this resource?*
* Tenant/workspace boundary (26.1) — *is this action within the right
  tenant/workspace boundary?*
* Read-only enforcement (26.2, this module) — *does this SQL actually carry no
  write / DDL / procedure / data-movement risk?*

Core security principle — **fail closed**: if the SQL is not provably a single
read-only ``SELECT`` (or ``WITH ... SELECT``), it is denied. No write, DDL,
procedure, transaction-control, or data-movement statement may pass "maybe it's
safe".

Before classifying, the SQL is lexed into code / string-literal / quoted-identifier
/ comment regions (``_sanitize``): comments are removed and string literals and
double-quoted identifiers are masked. Only *executable code* is then scanned. This
means a forbidden word that appears only as data (``SELECT 'please DROP it'``) or
as a quoted identifier (``SELECT * FROM "merge"``) is NOT a false positive, while a
``;`` or write verb in real executable position is still caught — including the
classic ``... '' ; DROP TABLE t; --`` injection tail, whose quotes balance and
leave the ``;``/``DROP`` in code position.

KNOWN LIMITATION (string layer): a write expressed as a *function call*
(``SELECT setval(...)``, ``SELECT lo_export(...)``, a CTE calling a writing
function) starts with SELECT and contains no write *verb*, so this string-level
gate classifies it ALLOW. Catching those requires an allowlist of safe functions
or a real parser (later sprint); the live execution path's DB-enforced read-only
session (``default_transaction_read_only=on`` in the PostgreSQL adapter) is the
backstop for that class. Treat this contract as the first, not the only, layer.

Out of scope (later sprints): query risk classifier (26.3), sensitive
table/column policy (26.4), PII/PHI detection (26.5), audit persistence (26.6),
approval workflow (26.7), prompt-injection/NL abuse defense (26.8), result
privacy / row limits (26.9), credential vault (26.10). No new DB adapter, no real
production execution, no API/UI, no tenant/RBAC/AuthN. This module imports no DB
driver, no SQL parser dependency, and performs no I/O.
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION = "sql_read_only_enforcement_contract_v1"

# Number of leading-keyword characters echoed for audit. Deliberately the leading
# SQL keyword only (e.g. SELECT / WITH / DROP) — never query content — so no
# string literal, value, or PII can leak through the result.
_PREFIX_MAX_LEN = 32


class SQLReadOnlyEnforcementContractError(ValueError):
    """Raised when read-only enforcement contract rules are violated."""
    pass


class SQLReadOnlyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class SQLReadOnlyReasonCode(str, Enum):
    # Allow reason
    READ_ONLY_SELECT = "read_only_select"
    # Deny reasons (fail closed)
    EMPTY_SQL = "empty_sql"
    MULTI_STATEMENT = "multi_statement"
    NON_SELECT_STATEMENT = "non_select_statement"
    FORBIDDEN_KEYWORD = "forbidden_keyword"
    UNSAFE_PROCEDURE = "unsafe_procedure"
    UNSAFE_DATA_MOVEMENT = "unsafe_data_movement"
    INVALID_SQL_TYPE = "invalid_sql_type"


# --- Keyword taxonomy -------------------------------------------------------
#
# Two classes of dangerous keyword, distinguished by WHERE they can appear in a
# statement that nonetheless begins with SELECT/WITH:
#
# * "anywhere" keywords can write from a NON-leading executable position without a
#   statement separator — DML inside a data-modifying CTE
#   (``WITH x AS (DELETE ... RETURNING ...) SELECT ...``) and ``SELECT ... INTO``.
#   These MUST be scanned across the whole (sanitized) statement.
# * "leading-only" keywords (DDL, privilege, maintenance, transaction control,
#   procedures, COPY, MERGE) are only meaningful as a statement's leading verb. A
#   leading occurrence is caught here (for a precise reason code); a non-leading
#   occurrence is either a separate statement (caught by the multi-statement
#   check) or a plain identifier — which, after sanitization, we deliberately do
#   NOT reject (e.g. a column literally named ``comment`` or ``lock``).
#
# Scanning only executable code (comments/literals/quoted-identifiers stripped)
# keeps this fail-closed for real writes while not rejecting ordinary reads.

_PROCEDURE_KEYWORDS = ("CALL", "EXECUTE", "EXEC")
_DML_KEYWORDS = ("INSERT", "UPDATE", "DELETE")
_DDL_TXN_KEYWORDS = (
    "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COMMENT",
    "REINDEX", "VACUUM", "REFRESH", "ANALYZE", "BEGIN", "COMMIT", "ROLLBACK",
    "SAVEPOINT", "DECLARE", "LOCK",
)
# COPY/MERGE move data but only ever lead a statement, so they live here.
_LEADING_DATA_MOVEMENT_KEYWORDS = ("COPY", "MERGE")

_KEYWORD_CATEGORY: Dict[str, SQLReadOnlyReasonCode] = {}
for _kw in _PROCEDURE_KEYWORDS:
    _KEYWORD_CATEGORY[_kw] = SQLReadOnlyReasonCode.UNSAFE_PROCEDURE
for _kw in _DML_KEYWORDS:
    _KEYWORD_CATEGORY[_kw] = SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD
for _kw in _DDL_TXN_KEYWORDS:
    _KEYWORD_CATEGORY[_kw] = SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD
for _kw in _LEADING_DATA_MOVEMENT_KEYWORDS:
    _KEYWORD_CATEGORY[_kw] = SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT
# INTO (SELECT ... INTO) is data movement and can appear non-leading.
_KEYWORD_CATEGORY["INTO"] = SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT

# Keywords scanned across the whole statement (non-leading executable writes).
_ANYWHERE_KEYWORDS = _DML_KEYWORDS + ("INTO",)
_ANYWHERE_KEYWORD_RE = re.compile(r"\b(" + "|".join(_ANYWHERE_KEYWORDS) + r")\b", re.IGNORECASE)

# A read-only statement must begin with SELECT or a WITH (CTE) that ultimately
# feeds a SELECT. A data-modifying CTE (e.g. WITH x AS (DELETE ...)) is still
# caught: its DML verb is an "anywhere" keyword scanned across the statement.
_READ_ONLY_START_RE = re.compile(r"(?is)^\s*(SELECT|WITH)\b")
_LEADING_TOKEN_RE = re.compile(r"^\s*([A-Za-z_]+)")
_WHITESPACE_RE = re.compile(r"\s+")


def _sanitize(sql: str) -> str:
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


def _normalize(sql: str) -> str:
    """Collapse all whitespace runs to single spaces and strip. Deterministic."""
    return _WHITESPACE_RE.sub(" ", sql).strip()


def _leading_keyword(normalized_core: str) -> Optional[str]:
    match = _LEADING_TOKEN_RE.match(normalized_core)
    if not match:
        return None
    return match.group(1).upper()[:_PREFIX_MAX_LEN]


@dataclass(frozen=True)
class SQLReadOnlyEnforcementRequest:
    """An immutable read-only enforcement request.

    ``sql`` is typed ``str`` but intentionally NOT type-checked in ``__post_init__``
    so that a non-string value still produces a deterministic deny
    (``INVALID_SQL_TYPE``) from ``enforce()`` rather than blowing up at
    construction — fail closed end to end. ``dialect`` is informational; this
    sprint's classifier is dialect-generic (the keyword set is a conservative
    union), so dialect does not change the decision.
    """
    version: str
    sql: str
    dialect: str = "generic"

    def __post_init__(self):
        if self.version != SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION:
            raise SQLReadOnlyEnforcementContractError(f"Invalid request version: {self.version}")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLReadOnlyEnforcementContractError("dialect must be a non-empty string")


@dataclass(frozen=True)
class SQLReadOnlyEnforcementResult:
    """An immutable, audit-grade, secret-free read-only decision.

    Deliberately carries NO raw SQL: only a SHA-256 hash (``sql_sha256``) and the
    leading keyword (``normalized_prefix``, e.g. ``SELECT`` / ``DROP``) — never
    query content, values, or literals. ``sql_sha256`` is ``None`` only when the
    input was not a string (nothing to hash); ``normalized_prefix`` is ``None`` for
    empty / non-string / keyword-less input.
    """
    version: str
    decision: SQLReadOnlyDecision
    reason_code: SQLReadOnlyReasonCode
    reason: str
    sql_sha256: Optional[str]
    normalized_prefix: Optional[str]
    dialect: str

    def __post_init__(self):
        if self.version != SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION:
            raise SQLReadOnlyEnforcementContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.decision, SQLReadOnlyDecision):
            raise SQLReadOnlyEnforcementContractError("decision must be a SQLReadOnlyDecision")
        if not isinstance(self.reason_code, SQLReadOnlyReasonCode):
            raise SQLReadOnlyEnforcementContractError("reason_code must be a SQLReadOnlyReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SQLReadOnlyEnforcementContractError("reason must be a non-empty string")
        if self.sql_sha256 is not None and (
            not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256)
        ):
            raise SQLReadOnlyEnforcementContractError("sql_sha256 must be a lowercase SHA-256 hex digest or None")
        if self.normalized_prefix is not None and not isinstance(self.normalized_prefix, str):
            raise SQLReadOnlyEnforcementContractError("normalized_prefix must be a string or None")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLReadOnlyEnforcementContractError("dialect must be a non-empty string")

    @property
    def is_read_only(self) -> bool:
        return self.decision == SQLReadOnlyDecision.ALLOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "sql_sha256": self.sql_sha256,
            "normalized_prefix": self.normalized_prefix,
            "dialect": self.dialect,
        }


class SQLReadOnlyEnforcementContract:
    """Deterministic, fail-closed read-only SQL classifier.

    Stateless: the decision is a pure function of the request. Order (fail-closed):

    1. Non-string SQL            -> DENY / INVALID_SQL_TYPE
    2. Empty / whitespace SQL    -> DENY / EMPTY_SQL
       (then comments are stripped and string literals / quoted identifiers are
        masked; steps 3-6 operate on executable code only)
    3. More than one statement   -> DENY / MULTI_STATEMENT
    4. Leading verb is a write/DDL/procedure/data-movement keyword
                                 -> DENY / FORBIDDEN_KEYWORD | UNSAFE_PROCEDURE | UNSAFE_DATA_MOVEMENT
    5. A non-leading executable write keyword (DML in a CTE, ``... INTO``)
                                 -> DENY / FORBIDDEN_KEYWORD | UNSAFE_DATA_MOVEMENT
    6. Does not start SELECT/WITH -> DENY / NON_SELECT_STATEMENT
    7. Otherwise                 -> ALLOW / READ_ONLY_SELECT

    A single trailing semicolon is tolerated; any other ``;`` (in code position)
    is multi-statement.
    """

    def enforce(self, request: SQLReadOnlyEnforcementRequest) -> SQLReadOnlyEnforcementResult:
        if not isinstance(request, SQLReadOnlyEnforcementRequest):
            raise SQLReadOnlyEnforcementContractError("request must be a SQLReadOnlyEnforcementRequest")

        sql = request.sql
        dialect = request.dialect

        # 1. Must be a string at all.
        if not isinstance(sql, str):
            return self._deny(SQLReadOnlyReasonCode.INVALID_SQL_TYPE,
                              "SQL must be a string.", None, None, dialect)

        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()

        # 2. Must be non-empty.
        if not sql.strip():
            return self._deny(SQLReadOnlyReasonCode.EMPTY_SQL,
                              "SQL is empty.", sql_hash, None, dialect)

        # Strip comments and mask literals/identifiers, then normalize whitespace.
        # Everything below operates on executable code only.
        sanitized = _normalize(_sanitize(sql))
        core = sanitized[:-1].strip() if sanitized.endswith(";") else sanitized
        prefix = _leading_keyword(core)

        # 3. Single statement only (one optional trailing semicolon already removed).
        if ";" in core:
            return self._deny(SQLReadOnlyReasonCode.MULTI_STATEMENT,
                              "Multiple SQL statements are not allowed; only a single SELECT is permitted.",
                              sql_hash, prefix, dialect)

        # 4. A dangerous leading verb (DDL / procedure / COPY / MERGE / DML / INTO).
        if prefix is not None and prefix in _KEYWORD_CATEGORY:
            reason_code = _KEYWORD_CATEGORY[prefix]
            return self._deny(reason_code, self._keyword_reason(reason_code, prefix),
                              sql_hash, prefix, dialect)

        # 5. A non-leading executable write (DML in a CTE, or SELECT ... INTO).
        match = _ANYWHERE_KEYWORD_RE.search(core)
        if match:
            keyword = match.group(1).upper()
            reason_code = _KEYWORD_CATEGORY[keyword]
            return self._deny(reason_code, self._keyword_reason(reason_code, keyword),
                              sql_hash, prefix, dialect)

        # 6. Must begin with SELECT or WITH (other keyword-free non-selects land here).
        if not _READ_ONLY_START_RE.match(core):
            return self._deny(SQLReadOnlyReasonCode.NON_SELECT_STATEMENT,
                              "Only read-only SELECT (or WITH ... SELECT) queries are allowed.",
                              sql_hash, prefix, dialect)

        # 7. A single read-only SELECT.
        return SQLReadOnlyEnforcementResult(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
            decision=SQLReadOnlyDecision.ALLOW,
            reason_code=SQLReadOnlyReasonCode.READ_ONLY_SELECT,
            reason="SQL is a single read-only SELECT statement.",
            sql_sha256=sql_hash,
            normalized_prefix=prefix,
            dialect=dialect,
        )

    @staticmethod
    def _keyword_reason(reason_code: SQLReadOnlyReasonCode, keyword: str) -> str:
        if reason_code == SQLReadOnlyReasonCode.UNSAFE_PROCEDURE:
            return f"Procedure/execution keyword '{keyword}' is not allowed in read-only execution."
        if reason_code == SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT:
            return f"Data-movement keyword '{keyword}' is not allowed in read-only execution."
        return f"Forbidden keyword '{keyword}' is not allowed in read-only execution."

    def _deny(
        self,
        reason_code: SQLReadOnlyReasonCode,
        reason: str,
        sql_sha256: Optional[str],
        normalized_prefix: Optional[str],
        dialect: str,
    ) -> SQLReadOnlyEnforcementResult:
        return SQLReadOnlyEnforcementResult(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
            decision=SQLReadOnlyDecision.DENY,
            reason_code=reason_code,
            reason=reason,
            sql_sha256=sql_sha256,
            normalized_prefix=normalized_prefix,
            dialect=dialect,
        )
