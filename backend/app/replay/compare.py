"""Baseline ve gozlenen kosunun saf karsilastirmasi (Sprint 27.4).

SAF: I/O yok, saat yok, rastgelelik yok. Tum tuple ciktilari siralidir.
Verdict EN CIDDI degisikligi adlandirir; delta'lar hepsini tasir.
"""
from typing import Optional, Tuple

from app.replay.contract import (
    ReplayBaseline,
    ReplayObserved,
    ReplayResult,
    RetrievalDelta,
    SecurityDelta,
    ValidationDelta,
)
from app.replay.verdicts import ReplayVerdict


def _sorted_tuple(values) -> Tuple[str, ...]:
    return tuple(sorted({str(v) for v in (values or ())}))


def _retrieval_delta(baseline: ReplayBaseline,
                     observed: ReplayObserved) -> RetrievalDelta:
    if baseline.retrieval_tables is None or observed.retrieval_tables is None:
        return RetrievalDelta(applicable=False)
    base = _sorted_tuple(baseline.retrieval_tables)
    obs = _sorted_tuple(observed.retrieval_tables)
    added = tuple(sorted(set(obs) - set(base)))
    removed = tuple(sorted(set(base) - set(obs)))
    return RetrievalDelta(
        applicable=True, baseline_tables=base, observed_tables=obs,
        added=added, removed=removed, changed=bool(added or removed))


def _validation_delta(baseline: ReplayBaseline,
                      observed: ReplayObserved) -> ValidationDelta:
    if baseline.validation_valid is None or observed.validation_valid is None:
        return ValidationDelta(applicable=False)
    base_issues = _sorted_tuple(baseline.validation_issue_types)
    obs_issues = _sorted_tuple(observed.validation_issue_types)
    changed = (baseline.validation_valid != observed.validation_valid
               or base_issues != obs_issues)
    return ValidationDelta(
        applicable=True,
        baseline_valid=baseline.validation_valid,
        observed_valid=observed.validation_valid,
        baseline_issue_types=base_issues,
        observed_issue_types=obs_issues,
        changed=changed)


def _security_delta(baseline: ReplayBaseline,
                    observed: ReplayObserved) -> SecurityDelta:
    if baseline.security_denied is None or observed.security_denied is None:
        return SecurityDelta(applicable=False)
    base = _sorted_tuple(baseline.security_denied)
    obs = _sorted_tuple(observed.security_denied)
    return SecurityDelta(applicable=True, baseline_denied=base,
                         observed_denied=obs, changed=base != obs)


def _notes(retrieval: RetrievalDelta, validation: ValidationDelta,
           security: SecurityDelta, observed: ReplayObserved) -> Tuple[str, ...]:
    notes = list(observed.notes or ())
    if not retrieval.applicable:
        notes.append("retrieval boyutu karsilastirilamadi (baseline ya da gozlem yok)")
    if not validation.applicable:
        notes.append("validation boyutu karsilastirilamadi (baseline ya da gozlem yok)")
    if not security.applicable:
        notes.append("security boyutu karsilastirilamadi (baseline ya da gozlem yok)")
    return tuple(notes)


def compare_replay(*, job_id: str, baseline: Optional[ReplayBaseline],
                   observed: ReplayObserved) -> ReplayResult:
    """Verdict onceligi (ilk eslesen kazanir):

    1 input_unavailable > 2 baseline_unavailable > 3 replay_failed >
    4 security_regression > 5 validation_regression > 6 retrieval_drift >
    7 validation_recovery > 8 identical
    """
    if not observed.input_available:
        return ReplayResult(
            job_id=job_id, verdict=ReplayVerdict.INPUT_UNAVAILABLE,
            baseline_trace_id=baseline.trace_id if baseline else None,
            notes=tuple(observed.notes or ()))

    if baseline is None:
        return ReplayResult(
            job_id=job_id, verdict=ReplayVerdict.BASELINE_UNAVAILABLE,
            notes=tuple(observed.notes or ()))

    retrieval = _retrieval_delta(baseline, observed)
    validation = _validation_delta(baseline, observed)
    security = _security_delta(baseline, observed)
    notes = _notes(retrieval, validation, security, observed)

    if observed.retrieval_error_code:
        return ReplayResult(
            job_id=job_id, verdict=ReplayVerdict.REPLAY_FAILED,
            baseline_trace_id=baseline.trace_id,
            retrieval=retrieval, validation=validation, security=security,
            error_code=observed.retrieval_error_code, notes=notes)

    if security.applicable and set(security.observed_denied) - set(security.baseline_denied):
        verdict = ReplayVerdict.SECURITY_REGRESSION
    elif (validation.applicable and validation.baseline_valid
          and not validation.observed_valid):
        verdict = ReplayVerdict.VALIDATION_REGRESSION
    elif retrieval.applicable and retrieval.changed:
        verdict = ReplayVerdict.RETRIEVAL_DRIFT
    elif (validation.applicable and not validation.baseline_valid
          and validation.observed_valid):
        verdict = ReplayVerdict.VALIDATION_RECOVERY
    else:
        verdict = ReplayVerdict.IDENTICAL

    return ReplayResult(
        job_id=job_id, verdict=verdict, baseline_trace_id=baseline.trace_id,
        retrieval=retrieval, validation=validation, security=security,
        notes=notes)
