"""Sprint 26.3 — Query Risk Classifier (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint assigns a *static*
(no execution) risk classification to a SQL query, deterministically and
contract-first. It is a **classifier, not a gate**: it returns a risk level plus
the signals that triggered it; it never allows or denies. Downstream consumers
(approval workflow 26.7, result/row limits 26.9, audit, observability) decide what
to do with the risk.

Where the Phase 7 gates answer yes/no questions — may this run (26.0), is it in
the right tenant (26.1), is it read-only (26.2) — 26.3 answers a *graded* one:

* Even if this query is read-only, how risky / expensive / dangerous is it, and why?

It also partially mitigates the documented limitation of the read-only contract
(26.2): a write expressed as a *function call* (``SELECT setval(...)``,
``SELECT lo_export(...)``, ``SELECT pg_terminate_backend(...)``) passes the
read-only string gate, but here it raises the ``SIDE_EFFECTING_FUNCTION`` signal
and a ``CRITICAL`` level — making the danger visible (not blocked) one layer up.

Core principle — **bias to higher risk on uncertainty** (the risk-grading form of
fail-closed): anything empty, non-string, comment-only, or not a recognizable
read query (``SELECT`` / ``WITH ... SELECT``) is ``CRITICAL`` /
``INVALID_OR_UNPARSEABLE``. "Unsure, so treat it as cheap/safe" is exactly what
this classifier refuses to do.

Out of scope (later sprints): sensitive table/column policy (26.4), PII/PHI
detection (26.5), audit persistence (26.6), approval workflow (26.7),
prompt-injection defense (26.8), result privacy / row-limit *enforcement* (26.9),
credential vault (26.10). No allow/deny decision, no real SQL parser dependency,
no EXPLAIN / cost measurement, no execution, no new adapter, no API/UI, no
tenant/RBAC/AuthN. Heuristics are deterministic regex over the shared
``_sql_text`` sanitizer (comments/literals stripped), so a keyword or function
name inside a string literal is never a false signal. This module performs no I/O.

KNOWN LIMITATIONS (regex heuristics, no parser — a sound fix needs a real parser
or catalog metadata, a later sprint):

* ``SIDE_EFFECTING_FUNCTION`` is a curated, non-exhaustive *denylist*; an unlisted
  writing function is not flagged. An allowlist of safe functions or
  ``pg_proc.provolatile`` would be sound.
* The classifier is **nesting-blind**: ``has_where`` / ``has_row_limit`` and the
  cartesian check are evaluated over the whole flattened statement, so a ``WHERE``
  or ``LIMIT`` inside a subquery/CTE suppresses the corresponding outer-scan signal
  (under-classification), and the comma-join cartesian rule (which fires only when
  there is no ``WHERE`` *anywhere*) can both over-fire on a small intentional cross
  join and go silent on a true cross product that happens to carry any ``WHERE``.
  Writes disguised as reads ARE caught (via the read-only contract composition);
  the cost-shape heuristics above remain best-effort until a parser lands.
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.security._sql_text import leading_keyword as _leading_keyword
from app.security._sql_text import to_executable_core as _to_executable_core
from app.security.sql_read_only_enforcement import (
    SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
    SQLReadOnlyDecision,
    SQLReadOnlyEnforcementContract,
    SQLReadOnlyEnforcementRequest,
)

# Reused to answer "is this actually a read?" — so a write/DDL/procedure/
# multi-statement disguised as a read (e.g. WITH x AS (...) INSERT INTO t SELECT ...)
# is graded CRITICAL instead of slipping through the leading-keyword check as a read.
_READ_ONLY_ENFORCER = SQLReadOnlyEnforcementContract()

SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION = "sql_query_risk_classifier_contract_v1"

# A query that ends up joining this many tables (explicit JOINs) is treated as
# structurally expensive.
_HIGH_JOIN_THRESHOLD = 4


class SQLQueryRiskClassifierContractError(ValueError):
    """Raised when query risk classifier contract rules are violated."""
    pass


class SQLQueryRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SQLQueryRiskSignal(str, Enum):
    # Declared in canonical output order (results are sorted by this order).
    SELECT_STAR = "select_star"
    NO_WHERE_FILTER = "no_where_filter"
    NO_ROW_LIMIT = "no_row_limit"
    CARTESIAN_JOIN = "cartesian_join"
    HIGH_JOIN_COUNT = "high_join_count"
    SIDE_EFFECTING_FUNCTION = "side_effecting_function"
    UNBOUNDED_RESULT = "unbounded_result"
    INVALID_OR_UNPARSEABLE = "invalid_or_unparseable"


# Each signal's inherent severity. The overall risk level is the MAX severity of
# the triggered signals (bias to higher risk); no signal -> LOW.
_SIGNAL_SEVERITY: Dict[SQLQueryRiskSignal, SQLQueryRiskLevel] = {
    SQLQueryRiskSignal.SELECT_STAR: SQLQueryRiskLevel.MEDIUM,
    SQLQueryRiskSignal.NO_WHERE_FILTER: SQLQueryRiskLevel.MEDIUM,
    SQLQueryRiskSignal.NO_ROW_LIMIT: SQLQueryRiskLevel.MEDIUM,
    SQLQueryRiskSignal.HIGH_JOIN_COUNT: SQLQueryRiskLevel.HIGH,
    SQLQueryRiskSignal.UNBOUNDED_RESULT: SQLQueryRiskLevel.HIGH,
    SQLQueryRiskSignal.CARTESIAN_JOIN: SQLQueryRiskLevel.CRITICAL,
    SQLQueryRiskSignal.SIDE_EFFECTING_FUNCTION: SQLQueryRiskLevel.CRITICAL,
    SQLQueryRiskSignal.INVALID_OR_UNPARSEABLE: SQLQueryRiskLevel.CRITICAL,
}

_LEVEL_ORDER: Dict[SQLQueryRiskLevel, int] = {
    SQLQueryRiskLevel.LOW: 0,
    SQLQueryRiskLevel.MEDIUM: 1,
    SQLQueryRiskLevel.HIGH: 2,
    SQLQueryRiskLevel.CRITICAL: 3,
}

# Canonical output ordering for signals (enum declaration order).
_SIGNAL_ORDER: Dict[SQLQueryRiskSignal, int] = {sig: i for i, sig in enumerate(SQLQueryRiskSignal)}

# Curated, non-exhaustive denylist of side-effecting / volatile / admin functions
# that a SELECT can call to write or otherwise affect server state. Matched as a
# function call ``name(`` in executable code (literals are already masked).
_SIDE_EFFECTING_FUNCTIONS = (
    "setval", "nextval",
    "lo_export", "lo_import", "lo_unlink", "lo_put", "lo_creat", "lo_create",
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "pg_terminate_backend", "pg_cancel_backend",
    "pg_reload_conf", "pg_rotate_logfile",
    "pg_switch_wal", "pg_switch_xlog",
    "pg_create_restore_point",
    "pg_drop_replication_slot",
    "pg_create_physical_replication_slot", "pg_create_logical_replication_slot",
    "pg_replication_origin_create", "pg_replication_origin_drop",
    "pg_logical_emit_message",
    "pg_advisory_lock", "pg_advisory_xact_lock", "pg_advisory_unlock",
    "pg_stat_statements_reset", "pg_stat_reset",
    # Filesystem / catalog reads, arbitrary-SQL, snapshot & xact introspection.
    "pg_stat_file", "pg_relation_filepath", "pg_relation_filenode",
    "txid_current", "txid_current_snapshot",
    "pg_export_snapshot", "pg_current_xact_id", "pg_current_xact_id_if_assigned",
)
# Function-name *families* where every member writes, reads server files, lists
# directories, or runs remote/arbitrary SQL — matched by prefix so we don't have to
# enumerate every variant. (No safe function shares these prefixes.)
_SIDE_EFFECTING_FAMILIES = (
    r"dblink\w*",        # dblink, dblink_exec, dblink_connect, dblink_send_query, ...
    r"pg_read_\w+",      # pg_read_file, pg_read_binary_file, pg_read_server_files
    r"pg_ls_\w+",        # pg_ls_dir, pg_ls_logdir, pg_ls_waldir, pg_ls_tmpdir, ...
    r"query_to_xml\w*",  # query_to_xml(...) executes an arbitrary SQL string
    r"cursor_to_xml\w*",
)
# Longest exact name first (word boundaries make this robust anyway), then the
# family patterns; require an opening parenthesis (a call, not an identifier).
_SIDE_EFFECTING_RE = re.compile(
    r"\b(?:"
    + "|".join(sorted(_SIDE_EFFECTING_FUNCTIONS, key=len, reverse=True) + list(_SIDE_EFFECTING_FAMILIES))
    + r")\s*\(",
    re.IGNORECASE,
)

_READ_QUERY_START_RE = re.compile(r"(?is)^\s*(SELECT|WITH)\b")
# SELECT * / SELECT DISTINCT * / a non-leading ", *" in the select list / t.* form.
_SELECT_STAR_RE = re.compile(r"(?i)(\bSELECT\s+(?:DISTINCT\s+|ALL\s+)?\*|,\s*\*|\b\w+\.\*)")
_FROM_RE = re.compile(r"(?i)\bFROM\b")
_WHERE_RE = re.compile(r"(?i)\bWHERE\b")
# Require the keyword in row-limit *clause position* (followed by a count / ALL /
# bind param / FIRST|NEXT) so a column or alias literally named "top"/"limit" does
# not falsely look like a row cap.
_ROW_LIMIT_RE = re.compile(
    r"(?i)(\bLIMIT\s+(\d|ALL\b|[:$?])|\bFETCH\s+(FIRST|NEXT)\b|\bTOP\s*[\d(]|\bROWNUM\b)"
)
_JOIN_RE = re.compile(r"(?i)\bJOIN\b")
_CROSS_JOIN_RE = re.compile(r"(?i)\bCROSS\s+JOIN\b")
# Top-level clause keywords that end the FROM clause.
_CLAUSE_BOUNDARY_RE = re.compile(
    r"(?i)\b(WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|FETCH|WINDOW|UNION|INTERSECT|EXCEPT)\b"
)


def _from_clause(core: str) -> str:
    """Return the FROM-clause text (between FROM and the next top-level clause),
    or ``""`` if there is no FROM."""
    m = _FROM_RE.search(core)
    if not m:
        return ""
    rest = core[m.end():]
    boundary = _CLAUSE_BOUNDARY_RE.search(rest)
    return rest[:boundary.start()] if boundary else rest


def _has_top_level_comma(text: str) -> bool:
    """True if ``text`` contains a comma at parenthesis depth 0 (a comma-join in a
    FROM clause, not a comma inside a function-arg or IN-list)."""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            return True
    return False


@dataclass(frozen=True)
class SQLQueryRiskRequest:
    """An immutable query-risk request.

    ``sql`` is typed ``str`` but intentionally NOT type-checked in ``__post_init__``
    so a non-string still yields a deterministic ``CRITICAL`` /
    ``INVALID_OR_UNPARSEABLE`` from ``classify()`` (bias to higher risk) instead of
    raising at construction. ``dialect`` is informational; the heuristics are
    dialect-generic this sprint.
    """
    version: str
    sql: str
    dialect: str = "generic"

    def __post_init__(self):
        if self.version != SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION:
            raise SQLQueryRiskClassifierContractError(f"Invalid request version: {self.version}")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLQueryRiskClassifierContractError("dialect must be a non-empty string")


@dataclass(frozen=True)
class SQLQueryRiskResult:
    """An immutable, audit-grade, secret-free risk classification.

    Carries NO raw SQL: only the risk level, the triggered signals (deterministic
    order, de-duplicated), a short reason, a SHA-256 hash, and the leading keyword
    (``normalized_prefix``). No allow/deny field — this is a classifier, not a gate.
    """
    version: str
    risk_level: SQLQueryRiskLevel
    signals: Tuple[SQLQueryRiskSignal, ...]
    reason: str
    sql_sha256: Optional[str]
    normalized_prefix: Optional[str]
    dialect: str

    def __post_init__(self):
        if self.version != SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION:
            raise SQLQueryRiskClassifierContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.risk_level, SQLQueryRiskLevel):
            raise SQLQueryRiskClassifierContractError("risk_level must be a SQLQueryRiskLevel")
        if not isinstance(self.signals, tuple):
            raise SQLQueryRiskClassifierContractError("signals must be a tuple")
        for sig in self.signals:
            if not isinstance(sig, SQLQueryRiskSignal):
                raise SQLQueryRiskClassifierContractError("each signal must be a SQLQueryRiskSignal")
        if len(set(self.signals)) != len(self.signals):
            raise SQLQueryRiskClassifierContractError("signals must be de-duplicated")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SQLQueryRiskClassifierContractError("reason must be a non-empty string")
        if self.sql_sha256 is not None and (
            not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256)
        ):
            raise SQLQueryRiskClassifierContractError("sql_sha256 must be a lowercase SHA-256 hex digest or None")
        if self.normalized_prefix is not None and not isinstance(self.normalized_prefix, str):
            raise SQLQueryRiskClassifierContractError("normalized_prefix must be a string or None")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLQueryRiskClassifierContractError("dialect must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "risk_level": self.risk_level.value,
            "signals": [s.value for s in self.signals],
            "reason": self.reason,
            "sql_sha256": self.sql_sha256,
            "normalized_prefix": self.normalized_prefix,
            "dialect": self.dialect,
        }


class SQLQueryRiskClassifier:
    """Deterministic, static SQL query risk classifier.

    Stateless: the classification is a pure function of the request. It does not
    allow or deny — it grades. The overall ``risk_level`` is the maximum severity
    of the triggered signals; with no signal the query is ``LOW``.

    Anything that is not a recognizable read query (non-string, empty, comment-only,
    or not starting ``SELECT`` / ``WITH``) short-circuits to ``CRITICAL`` /
    ``INVALID_OR_UNPARSEABLE`` (bias to higher risk).
    """

    def classify(self, request: SQLQueryRiskRequest) -> SQLQueryRiskResult:
        if not isinstance(request, SQLQueryRiskRequest):
            raise SQLQueryRiskClassifierContractError("request must be a SQLQueryRiskRequest")

        sql = request.sql
        dialect = request.dialect

        if not isinstance(sql, str):
            return self._result([SQLQueryRiskSignal.INVALID_OR_UNPARSEABLE], None, None, dialect,
                                reason="SQL is not a string; cannot assess risk (treated as critical).")

        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        core = _to_executable_core(sql)
        prefix = _leading_keyword(core)

        # Not a recognizable read query -> we do not assess it; bias to critical.
        if not core or not _READ_QUERY_START_RE.match(core):
            return self._result([SQLQueryRiskSignal.INVALID_OR_UNPARSEABLE], sql_hash, prefix, dialect,
                                reason="SQL is empty or not a recognizable read query (treated as critical).")

        # It *starts* like a read, but is it actually one? Reuse the read-only
        # enforcement contract (26.2) so a write/DDL/procedure/multi-statement
        # hidden behind a leading SELECT/WITH (e.g. WITH x AS (...) INSERT INTO ...,
        # SELECT ... INTO ..., or "SELECT 1; DELETE ...") is graded critical rather
        # than slipping through the leading-keyword check as a benign read.
        read_only = _READ_ONLY_ENFORCER.enforce(
            SQLReadOnlyEnforcementRequest(
                version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION, sql=sql, dialect=dialect)
        )
        if read_only.decision == SQLReadOnlyDecision.DENY:
            return self._result([SQLQueryRiskSignal.INVALID_OR_UNPARSEABLE], sql_hash, prefix, dialect,
                                reason="SQL is not a read-only query (write/DDL/procedure/multi-statement "
                                       "detected); treated as critical.")

        signals: List[SQLQueryRiskSignal] = []

        has_from = bool(_FROM_RE.search(core))
        has_where = bool(_WHERE_RE.search(core))
        has_row_limit = bool(_ROW_LIMIT_RE.search(core))
        join_count = len(_JOIN_RE.findall(core))

        if _SELECT_STAR_RE.search(core):
            signals.append(SQLQueryRiskSignal.SELECT_STAR)
        if has_from and not has_where:
            signals.append(SQLQueryRiskSignal.NO_WHERE_FILTER)
        if has_from and not has_row_limit:
            signals.append(SQLQueryRiskSignal.NO_ROW_LIMIT)

        # Cartesian product: an explicit CROSS JOIN, or a comma-join in the FROM
        # clause with no WHERE at all (an unfiltered cross product).
        is_cartesian = bool(_CROSS_JOIN_RE.search(core)) or (
            not has_where and _has_top_level_comma(_from_clause(core))
        )
        if is_cartesian:
            signals.append(SQLQueryRiskSignal.CARTESIAN_JOIN)
        if join_count >= _HIGH_JOIN_THRESHOLD:
            signals.append(SQLQueryRiskSignal.HIGH_JOIN_COUNT)
        if _SIDE_EFFECTING_RE.search(core):
            signals.append(SQLQueryRiskSignal.SIDE_EFFECTING_FUNCTION)
        # Multi-table read with no row cap -> potentially large result.
        if join_count >= 1 and not has_row_limit:
            signals.append(SQLQueryRiskSignal.UNBOUNDED_RESULT)

        return self._result(signals, sql_hash, prefix, dialect)

    def _result(
        self,
        signals: List[SQLQueryRiskSignal],
        sql_sha256: Optional[str],
        normalized_prefix: Optional[str],
        dialect: str,
        reason: Optional[str] = None,
    ) -> SQLQueryRiskResult:
        # De-duplicate and order deterministically by canonical signal order.
        ordered = tuple(sorted(set(signals), key=lambda s: _SIGNAL_ORDER[s]))
        level = self._max_severity(ordered)
        if reason is None:
            if ordered:
                reason = (f"Query risk classified as {level.value} "
                          f"({len(ordered)} signal(s): {', '.join(s.value for s in ordered)}).")
            else:
                reason = "Query risk classified as low (no risk signals detected)."
        return SQLQueryRiskResult(
            version=SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION,
            risk_level=level,
            signals=ordered,
            reason=reason,
            sql_sha256=sql_sha256,
            normalized_prefix=normalized_prefix,
            dialect=dialect,
        )

    @staticmethod
    def _max_severity(signals: Tuple[SQLQueryRiskSignal, ...]) -> SQLQueryRiskLevel:
        level = SQLQueryRiskLevel.LOW
        for sig in signals:
            sev = _SIGNAL_SEVERITY[sig]
            if _LEVEL_ORDER[sev] > _LEVEL_ORDER[level]:
                level = sev
        return level
