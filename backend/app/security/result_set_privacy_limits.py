"""Sprint 26.9 — Result-Set Privacy & Limits Contract (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. The FIRST Phase 7 contract that
operates on the **post-execution result set** — the actual rows and column names a
query returned — rather than SQL (26.0-26.5) or natural language (26.8). One
``evaluate()`` produces a unified result with two distinct concerns:

* **Limits (a GATE):** a caller-supplied policy (``max_rows`` / ``max_bytes`` /
  ``max_columns``) decides ALLOW (return whole), TRUNCATE (return a row prefix), or
  DENY (refuse). Bounds result size for cost / transport / denial-of-wallet.
* **Privacy (an advisory SIGNAL):** scan the returned cell values for PII/PHI using
  the shared 26.5 value-format heuristics; report, per column, which categories
  appeared, how many cells matched, and the highest confidence. NOT a gate — never
  changes the limit decision. The value-format heuristics surface PII categories
  only (email, SSN, IBAN, credit card, phone); PHI categories require
  name/declared-column signals this contract does not see, so ``has_phi`` is
  effectively always ``False`` in 26.9.

Core principle — the contract carries and cuts **no data**. It returns a
``kept_rows`` DECISION; the caller applies ``rows[:kept_rows]``. The result never
holds a raw cell value or a sample row (secret-free, like 26.5). Performs no I/O.

Out of scope (later / deliberate): actual row slicing / transport (caller applies
the decision); query execution / adapters; column *truncation* (a column overage is
always DENY — narrowing the schema is unacceptable silent data loss); masking /
redaction (a remedy, not this detector); streaming; a real cell type system (cells
are opaque, str-cast for scan + byte estimate); ML / semantic classification;
credential vault (26.10); policy eval (26.11). See module-level limitations notes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.security._pii_value_scan import (
    SQLDataClass,
    SQLPiiPhiCategory,
    SQLPiiPhiConfidence,
    _CATEGORY_DATA_CLASS,
    _CONFIDENCE_ORDER,
    scan_value_categories,
)

RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION = "result_set_privacy_limits_contract_v1"


class ResultSetPrivacyLimitsContractError(ValueError):
    """Raised when result-set privacy/limits contract rules are violated."""
    pass


class ResultSetLimitDisposition(str, Enum):
    ALLOW = "allow"          # returned whole
    TRUNCATE = "truncate"    # return a row prefix (kept_rows < total_rows)
    DENY = "deny"            # refuse the result


class ResultSetLimitReasonCode(str, Enum):
    WITHIN_LIMITS = "within_limits"
    EMPTY_RESULT = "empty_result"
    ROW_CAP_TRUNCATED = "row_cap_truncated"
    BYTE_CAP_TRUNCATED = "byte_cap_truncated"
    ROW_CAP_DENIED = "row_cap_denied"
    BYTE_CAP_DENIED = "byte_cap_denied"
    COLUMN_CAP_DENIED = "column_cap_denied"


# Deterministic low->high ordering for the limit disposition.
_LIMIT_DISPOSITION_ORDER: Dict[ResultSetLimitDisposition, int] = {
    ResultSetLimitDisposition.ALLOW: 0,
    ResultSetLimitDisposition.TRUNCATE: 1,
    ResultSetLimitDisposition.DENY: 2,
}


def _check_opt_nonneg_int(value: Any, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResultSetPrivacyLimitsContractError(
            f"{field} must be a non-negative int or None, got {value!r}")


@dataclass(frozen=True)
class ResultSetLimitPolicy:
    """Caller-supplied, frozen limit policy. None on any cap = that dimension is
    unbounded. ``truncate_allowed`` governs the row/byte overage remedy: True allows
    a row-prefix TRUNCATE; False makes any overage a DENY. (Column overage is always
    DENY regardless — see the gate algorithm.)"""
    max_rows: Optional[int] = None
    max_bytes: Optional[int] = None
    max_columns: Optional[int] = None
    truncate_allowed: bool = False

    def __post_init__(self) -> None:
        _check_opt_nonneg_int(self.max_rows, "max_rows")
        _check_opt_nonneg_int(self.max_bytes, "max_bytes")
        _check_opt_nonneg_int(self.max_columns, "max_columns")
        if not isinstance(self.truncate_allowed, bool):
            raise ResultSetPrivacyLimitsContractError("truncate_allowed must be a bool")


@dataclass(frozen=True)
class ResultSetColumnPrivacy:
    """Per-column PII/PHI summary. Secret-free: a category + a COUNT, never a value."""
    column_index: int
    column_name: str
    category: SQLPiiPhiCategory
    matched_cell_count: int
    highest_confidence: SQLPiiPhiConfidence
    data_class: SQLDataClass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_index": self.column_index,
            "column_name": self.column_name,
            "category": self.category.value,
            "matched_cell_count": self.matched_cell_count,
            "highest_confidence": self.highest_confidence.value,
            "data_class": self.data_class.value,
        }


@dataclass(frozen=True)
class ResultSetPrivacyLimitsRequest:
    """An immutable request: the returned column names, the returned rows
    (row-major; each row aligns positionally to ``columns``), and the limit policy.
    Cell values are opaque ``Any`` (str-cast for scanning + byte estimation)."""
    version: str
    columns: Tuple[str, ...]
    rows: Tuple[Tuple[Any, ...], ...]
    policy: ResultSetLimitPolicy

    def __post_init__(self) -> None:
        if self.version != RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION:
            raise ResultSetPrivacyLimitsContractError(
                f"Invalid request version: {self.version}")
        if not isinstance(self.columns, tuple) or not all(isinstance(c, str) for c in self.columns):
            raise ResultSetPrivacyLimitsContractError("columns must be a tuple of str")
        if not isinstance(self.rows, tuple) or not all(isinstance(r, tuple) for r in self.rows):
            raise ResultSetPrivacyLimitsContractError("rows must be a tuple of tuples")
        if not isinstance(self.policy, ResultSetLimitPolicy):
            raise ResultSetPrivacyLimitsContractError("policy must be a ResultSetLimitPolicy")


@dataclass(frozen=True)
class ResultSetPrivacyLimitsResult:
    """An immutable, audit-grade, secret-free result. Carries the limit GATE decision
    (disposition + reason + ``kept_rows`` — the caller slices ``rows[:kept_rows]``)
    and the advisory privacy SIGNAL (per-column summaries + rollups). No raw cell
    value and no sample row are ever present."""
    version: str
    limit_disposition: ResultSetLimitDisposition
    limit_reason_code: ResultSetLimitReasonCode
    total_rows: int
    total_columns: int
    estimated_bytes: int
    kept_rows: int
    truncated: bool
    column_privacy: Tuple[ResultSetColumnPrivacy, ...]
    privacy_categories: Tuple[SQLPiiPhiCategory, ...]
    highest_privacy_confidence: Optional[SQLPiiPhiConfidence]
    has_phi: bool
    reason: str

    def __post_init__(self) -> None:
        if self.version != RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION:
            raise ResultSetPrivacyLimitsContractError(
                f"Invalid result version: {self.version}")
        if not isinstance(self.limit_disposition, ResultSetLimitDisposition):
            raise ResultSetPrivacyLimitsContractError("limit_disposition must be a ResultSetLimitDisposition")
        if not isinstance(self.limit_reason_code, ResultSetLimitReasonCode):
            raise ResultSetPrivacyLimitsContractError("limit_reason_code must be a ResultSetLimitReasonCode")
        if not isinstance(self.column_privacy, tuple):
            raise ResultSetPrivacyLimitsContractError("column_privacy must be a tuple")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ResultSetPrivacyLimitsContractError("reason must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "limit_disposition": self.limit_disposition.value,
            "limit_reason_code": self.limit_reason_code.value,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "estimated_bytes": self.estimated_bytes,
            "kept_rows": self.kept_rows,
            "truncated": self.truncated,
            "column_privacy": [c.to_dict() for c in self.column_privacy],
            "privacy_categories": [c.value for c in self.privacy_categories],
            "highest_privacy_confidence": (
                self.highest_privacy_confidence.value
                if self.highest_privacy_confidence is not None else None),
            "has_phi": self.has_phi,
            "reason": self.reason,
        }


def _row_bytes(row: Tuple[Any, ...]) -> int:
    """UTF-8 byte estimate for one row: sum over cells of len(str(cell)) bytes.
    None cells str-cast to 'None' (a documented approximation). Column names are
    not counted — data, not headers, is the size concern."""
    return sum(len(str(cell).encode("utf-8")) for cell in row)


def _byte_prefix(row_sizes: List[int], max_bytes: Optional[int]) -> int:
    """Largest k such that the first k rows fit within max_bytes (all rows if
    max_bytes is None)."""
    if max_bytes is None:
        return len(row_sizes)
    acc = 0
    k = 0
    for size in row_sizes:
        if acc + size > max_bytes:
            break
        acc += size
        k += 1
    return k


def _evaluate_limits(columns: Tuple[str, ...], rows: Tuple[Tuple[Any, ...], ...],
                     policy: ResultSetLimitPolicy) -> Tuple[ResultSetLimitDisposition, ResultSetLimitReasonCode, int, int]:
    """Deterministic limit gate. Order matters: column cap FIRST (always DENY on
    overage), then empty-result, then the longest row prefix satisfying BOTH the row
    and byte caps. Returns (disposition, reason_code, kept_rows, estimated_bytes)."""
    total_rows = len(rows)
    total_columns = len(columns)
    row_sizes = [_row_bytes(r) for r in rows]
    estimated_bytes = sum(row_sizes)

    # (1) Column cap FIRST — always DENY on overage, regardless of truncate_allowed
    # (narrowing the schema is unacceptable silent data loss).
    if policy.max_columns is not None and total_columns > policy.max_columns:
        return (ResultSetLimitDisposition.DENY,
                ResultSetLimitReasonCode.COLUMN_CAP_DENIED, 0, estimated_bytes)

    # (2) Empty result.
    if total_rows == 0:
        return (ResultSetLimitDisposition.ALLOW,
                ResultSetLimitReasonCode.EMPTY_RESULT, 0, estimated_bytes)

    # (3) Row/byte caps — longest leading prefix satisfying both.
    row_prefix = total_rows if policy.max_rows is None else min(total_rows, policy.max_rows)
    byte_prefix = _byte_prefix(row_sizes, policy.max_bytes)
    kept = min(row_prefix, byte_prefix)

    if kept >= total_rows:
        return (ResultSetLimitDisposition.ALLOW,
                ResultSetLimitReasonCode.WITHIN_LIMITS, total_rows, estimated_bytes)

    # Over limit. Byte cap is binding if it produced the (weakly) smaller prefix
    # (tie -> byte, per design).
    byte_binding = policy.max_bytes is not None and byte_prefix <= row_prefix

    if policy.truncate_allowed and kept > 0:
        code = (ResultSetLimitReasonCode.BYTE_CAP_TRUNCATED if byte_binding
                else ResultSetLimitReasonCode.ROW_CAP_TRUNCATED)
        return (ResultSetLimitDisposition.TRUNCATE, code, kept, estimated_bytes)

    # DENY: truncate not allowed, OR truncate allowed but kept == 0 (fail-closed:
    # cannot return even one row within the byte budget).
    code = (ResultSetLimitReasonCode.BYTE_CAP_DENIED if byte_binding
            else ResultSetLimitReasonCode.ROW_CAP_DENIED)
    return (ResultSetLimitDisposition.DENY, code, 0, estimated_bytes)


def _scan_privacy(columns: Tuple[str, ...], rows: Tuple[Tuple[Any, ...], ...]) -> Tuple[Tuple[ResultSetColumnPrivacy, ...], Tuple[SQLPiiPhiCategory, ...], Optional[SQLPiiPhiConfidence], bool]:
    """Advisory PII/PHI signal over the FULL result set (column-major). For each
    column, scan every cell (skip None / empty / whitespace; str-cast otherwise) via
    the shared value-format heuristics. Emit one ResultSetColumnPrivacy per
    (column, category) with >=1 match. Secret-free: a category + a count, never a
    value. Returns (column_privacy, privacy_categories, highest_confidence, has_phi).
    """
    records: List[ResultSetColumnPrivacy] = []
    for idx, col_name in enumerate(columns):
        count_by_cat: Dict[SQLPiiPhiCategory, int] = {}
        conf_by_cat: Dict[SQLPiiPhiCategory, SQLPiiPhiConfidence] = {}
        for row in rows:
            if idx >= len(row):
                continue
            cell = row[idx]
            if cell is None:
                continue
            text = str(cell)
            if not text.strip():
                continue
            # Max confidence per category within this single cell (count the cell once).
            cell_cats: Dict[SQLPiiPhiCategory, SQLPiiPhiConfidence] = {}
            for category, confidence in scan_value_categories(text):
                if (category not in cell_cats
                        or _CONFIDENCE_ORDER[confidence] > _CONFIDENCE_ORDER[cell_cats[category]]):
                    cell_cats[category] = confidence
            for category, confidence in cell_cats.items():
                count_by_cat[category] = count_by_cat.get(category, 0) + 1
                if (category not in conf_by_cat
                        or _CONFIDENCE_ORDER[confidence] > _CONFIDENCE_ORDER[conf_by_cat[category]]):
                    conf_by_cat[category] = confidence
        for category in count_by_cat:
            records.append(ResultSetColumnPrivacy(
                column_index=idx, column_name=col_name, category=category,
                matched_cell_count=count_by_cat[category],
                highest_confidence=conf_by_cat[category],
                data_class=_CATEGORY_DATA_CLASS[category]))

    # Order: PHI before PII, then column_index, then category value.
    records.sort(key=lambda r: (
        0 if r.data_class == SQLDataClass.PHI else 1, r.column_index, r.category.value))

    column_privacy = tuple(records)
    privacy_categories = tuple(sorted({r.category for r in records}, key=lambda c: c.value))
    has_phi = any(r.data_class == SQLDataClass.PHI for r in records)
    highest = (max((r.highest_confidence for r in records),
                   key=lambda c: _CONFIDENCE_ORDER[c]) if records else None)
    return column_privacy, privacy_categories, highest, has_phi


class ResultSetPrivacyLimitsContract:
    """Deterministic, stateless contract over a post-execution result set. The
    result is a pure function of the request. The limit GATE and the privacy SIGNAL
    are independent — neither reads the other's output; a DENY result still carries
    the full privacy summary.
    """

    def evaluate(self, request: ResultSetPrivacyLimitsRequest) -> ResultSetPrivacyLimitsResult:
        if not isinstance(request, ResultSetPrivacyLimitsRequest):
            raise ResultSetPrivacyLimitsContractError(
                "request must be a ResultSetPrivacyLimitsRequest")

        columns = request.columns
        rows = request.rows

        disposition, reason_code, kept_rows, estimated_bytes = _evaluate_limits(
            columns, rows, request.policy)
        column_privacy, privacy_categories, highest_conf, has_phi = _scan_privacy(
            columns, rows)

        truncated = disposition == ResultSetLimitDisposition.TRUNCATE
        total_rows = len(rows)
        total_columns = len(columns)

        privacy_summary = (
            f"{len(privacy_categories)} privacy category(ies) "
            f"(has_phi={has_phi})" if privacy_categories else "no privacy signal")
        reason = (
            f"Limit {disposition.value} ({reason_code.value}): "
            f"kept {kept_rows}/{total_rows} row(s), {total_columns} column(s), "
            f"~{estimated_bytes} bytes. Privacy: {privacy_summary}.")

        return ResultSetPrivacyLimitsResult(
            version=RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION,
            limit_disposition=disposition,
            limit_reason_code=reason_code,
            total_rows=total_rows,
            total_columns=total_columns,
            estimated_bytes=estimated_bytes,
            kept_rows=kept_rows,
            truncated=truncated,
            column_privacy=column_privacy,
            privacy_categories=privacy_categories,
            highest_privacy_confidence=highest_conf,
            has_phi=has_phi,
            reason=reason,
        )
