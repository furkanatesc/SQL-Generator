"""Karsilastirma ve verdict onceligi testleri (Sprint 27.4 T3)."""
import pytest

from app.replay import (
    ReplayBaseline,
    ReplayObserved,
    ReplayVerdict,
    compare_replay,
)


def _baseline(**kw):
    defaults = dict(
        trace_id="trace_abc",
        terminal_status="completed",
        retrieval_tables=("customers", "orders"),
        validation_valid=True,
        validation_issue_types=(),
        security_denied=(),
    )
    defaults.update(kw)
    return ReplayBaseline(**defaults)


def _observed(**kw):
    defaults = dict(
        input_available=True,
        retrieval_tables=("customers", "orders"),
        retrieval_error_code=None,
        validation_valid=True,
        validation_issue_types=(),
        security_denied=(),
    )
    defaults.update(kw)
    return ReplayObserved(**defaults)


def test_identical_when_nothing_changed():
    result = compare_replay(job_id="j1", baseline=_baseline(), observed=_observed())
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert result.baseline_trace_id == "trace_abc"
    assert result.retrieval.changed is False
    assert result.validation.changed is False
    assert result.security.changed is False


def test_input_unavailable_wins_over_everything():
    result = compare_replay(
        job_id="j1", baseline=_baseline(),
        observed=_observed(input_available=False, retrieval_error_code="x",
                           validation_valid=False, security_denied=("boom",)))
    assert result.verdict == ReplayVerdict.INPUT_UNAVAILABLE


def test_baseline_unavailable_when_no_baseline():
    result = compare_replay(job_id="j1", baseline=None, observed=_observed())
    assert result.verdict == ReplayVerdict.BASELINE_UNAVAILABLE
    assert result.baseline_trace_id is None


def test_replay_failed_carries_error_code():
    result = compare_replay(
        job_id="j1", baseline=_baseline(),
        observed=_observed(retrieval_error_code="schema_pruning_failed",
                           retrieval_tables=None))
    assert result.verdict == ReplayVerdict.REPLAY_FAILED
    assert result.error_code == "schema_pruning_failed"


def test_security_regression_beats_validation_and_retrieval():
    result = compare_replay(
        job_id="j1", baseline=_baseline(),
        observed=_observed(security_denied=("unsafe_sandbox_rejected",),
                           validation_valid=False,
                           retrieval_tables=("customers",)))
    assert result.verdict == ReplayVerdict.SECURITY_REGRESSION
    # delta'lar DIGER degisiklikleri de tasir — sessiz dusurme yok
    assert result.validation.changed is True
    assert result.retrieval.changed is True
    assert result.retrieval.removed == ("orders",)


def test_validation_regression_beats_retrieval_drift():
    result = compare_replay(
        job_id="j1", baseline=_baseline(),
        observed=_observed(validation_valid=False,
                           validation_issue_types=("missing_column",),
                           retrieval_tables=("customers",)))
    assert result.verdict == ReplayVerdict.VALIDATION_REGRESSION
    assert result.retrieval.changed is True


def test_retrieval_drift_is_set_based_not_order_based():
    result = compare_replay(
        job_id="j1",
        baseline=_baseline(retrieval_tables=("customers", "orders")),
        observed=_observed(retrieval_tables=("orders", "customers")))
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert result.retrieval.changed is False


def test_retrieval_drift_reports_added_and_removed_sorted():
    result = compare_replay(
        job_id="j1",
        baseline=_baseline(retrieval_tables=("customers", "orders")),
        observed=_observed(retrieval_tables=("orders", "products", "audit")))
    assert result.verdict == ReplayVerdict.RETRIEVAL_DRIFT
    assert result.retrieval.added == ("audit", "products")
    assert result.retrieval.removed == ("customers",)


def test_validation_recovery_when_invalid_becomes_valid():
    result = compare_replay(
        job_id="j1",
        baseline=_baseline(validation_valid=False,
                           validation_issue_types=("syntax_error",)),
        observed=_observed(validation_valid=True))
    assert result.verdict == ReplayVerdict.VALIDATION_RECOVERY


def test_dimension_not_applicable_when_baseline_missing_it():
    result = compare_replay(
        job_id="j1",
        baseline=_baseline(retrieval_tables=None),
        observed=_observed(retrieval_tables=("orders",)))
    assert result.retrieval.applicable is False
    assert result.retrieval.changed is False
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert any("retrieval" in n for n in result.notes)


def test_dimension_not_applicable_when_observed_missing_it():
    result = compare_replay(
        job_id="j1", baseline=_baseline(),
        observed=_observed(validation_valid=None, validation_issue_types=None))
    assert result.validation.applicable is False
    assert result.verdict == ReplayVerdict.IDENTICAL


def test_security_recovery_is_reported_as_change_but_not_regression():
    result = compare_replay(
        job_id="j1",
        baseline=_baseline(security_denied=("unsafe_sandbox_rejected",)),
        observed=_observed(security_denied=()))
    assert result.security.changed is True
    assert result.verdict == ReplayVerdict.IDENTICAL


def test_result_version_and_job_id_are_set():
    result = compare_replay(job_id="j42", baseline=_baseline(), observed=_observed())
    assert result.job_id == "j42"
    assert result.version == "query_replay_v1"


def test_compare_is_deterministic():
    args = dict(job_id="j1", baseline=_baseline(), observed=_observed(
        retrieval_tables=("orders", "products", "audit")))
    assert compare_replay(**args).to_payload() == compare_replay(**args).to_payload()
