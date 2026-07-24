"""Replay sozlesmesi — frozen record'lar (Sprint 27.4).

Tum tuple alanlari SIRALI tutulur; ayni girdi her zaman ayni payload'i uretir.
to_payload() JSON-safe'tir: enum'lar .value ile plain string'e, tuple'lar
listeye doner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.replay.verdicts import REPLAY_CONTRACT_VERSION, ReplayVerdict


@dataclass(frozen=True)
class RetrievalDelta:
    """Secilen tablo kumesindeki fark. Karsilastirma KUME tabanlidir."""

    applicable: bool = True
    baseline_tables: Tuple[str, ...] = ()
    observed_tables: Tuple[str, ...] = ()
    added: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()
    changed: bool = False

    def to_payload(self) -> dict:
        return {
            "applicable": self.applicable,
            "baseline_tables": list(self.baseline_tables),
            "observed_tables": list(self.observed_tables),
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": self.changed,
        }


@dataclass(frozen=True)
class ValidationDelta:
    """SQL'in gecerliligindeki fark. issue MESAJLARI karsilastirmaya girmez."""

    applicable: bool = True
    baseline_valid: Optional[bool] = None
    observed_valid: Optional[bool] = None
    baseline_issue_types: Tuple[str, ...] = ()
    observed_issue_types: Tuple[str, ...] = ()
    changed: bool = False

    def to_payload(self) -> dict:
        return {
            "applicable": self.applicable,
            "baseline_valid": self.baseline_valid,
            "observed_valid": self.observed_valid,
            "baseline_issue_types": list(self.baseline_issue_types),
            "observed_issue_types": list(self.observed_issue_types),
            "changed": self.changed,
        }


@dataclass(frozen=True)
class SecurityDelta:
    """Guvenlik reddi (guardrail / sandbox safety) farki."""

    applicable: bool = True
    baseline_denied: Tuple[str, ...] = ()
    observed_denied: Tuple[str, ...] = ()
    changed: bool = False

    def to_payload(self) -> dict:
        return {
            "applicable": self.applicable,
            "baseline_denied": list(self.baseline_denied),
            "observed_denied": list(self.observed_denied),
            "changed": self.changed,
        }


@dataclass(frozen=True)
class ReplayBaseline:
    """O gunku end_to_end trace'ten cikarilan kiyas tarafi.

    None degerler "o boyut olculemedi" demektir (span SKIPPED ya da yok).
    """

    trace_id: Optional[str] = None
    terminal_status: Optional[str] = None
    retrieval_tables: Optional[Tuple[str, ...]] = None
    validation_valid: Optional[bool] = None
    validation_issue_types: Optional[Tuple[str, ...]] = None
    security_denied: Optional[Tuple[str, ...]] = None

    def to_payload(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "terminal_status": self.terminal_status,
            "retrieval_tables": (None if self.retrieval_tables is None
                                 else list(self.retrieval_tables)),
            "validation_valid": self.validation_valid,
            "validation_issue_types": (None if self.validation_issue_types is None
                                       else list(self.validation_issue_types)),
            "security_denied": (None if self.security_denied is None
                                else list(self.security_denied)),
        }


@dataclass(frozen=True)
class ReplayObserved:
    """Bugunun koduyla olculen taraf."""

    input_available: bool = True
    retrieval_tables: Optional[Tuple[str, ...]] = None
    retrieval_error_code: Optional[str] = None
    validation_valid: Optional[bool] = None
    validation_issue_types: Optional[Tuple[str, ...]] = None
    security_denied: Optional[Tuple[str, ...]] = None
    notes: Tuple[str, ...] = ()

    def to_payload(self) -> dict:
        return {
            "input_available": self.input_available,
            "retrieval_tables": (None if self.retrieval_tables is None
                                 else list(self.retrieval_tables)),
            "retrieval_error_code": self.retrieval_error_code,
            "validation_valid": self.validation_valid,
            "validation_issue_types": (None if self.validation_issue_types is None
                                       else list(self.validation_issue_types)),
            "security_denied": (None if self.security_denied is None
                                else list(self.security_denied)),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ReplayResult:
    """Tek bir replay kosusunun tam sonucu."""

    job_id: str
    verdict: ReplayVerdict
    version: str = REPLAY_CONTRACT_VERSION
    baseline_trace_id: Optional[str] = None
    retrieval: Optional[RetrievalDelta] = None
    validation: Optional[ValidationDelta] = None
    security: Optional[SecurityDelta] = None
    error_code: Optional[str] = None
    notes: Tuple[str, ...] = ()

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "job_id": self.job_id,
            # Sinirda PLAIN STRING (enum degil) — 27.2.1/27.3 deseni.
            "verdict": self.verdict.value,
            "baseline_trace_id": self.baseline_trace_id,
            "retrieval": None if self.retrieval is None else self.retrieval.to_payload(),
            "validation": None if self.validation is None else self.validation.to_payload(),
            "security": None if self.security is None else self.security.to_payload(),
            "error_code": self.error_code,
            "notes": list(self.notes),
        }
