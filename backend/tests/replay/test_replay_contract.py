"""Replay sözleşmesi testleri (Sprint 27.4 T1)."""
import json

import pytest

from app.replay import (
    REPLAY_CONTRACT_VERSION,
    ReplayBaseline,
    ReplayObserved,
    ReplayResult,
    ReplayVerdict,
    RetrievalDelta,
    SecurityDelta,
    ValidationDelta,
)


def test_verdict_members_are_plain_string_values():
    assert ReplayVerdict.IDENTICAL == "identical"
    assert ReplayVerdict.RETRIEVAL_DRIFT == "retrieval_drift"
    assert ReplayVerdict.VALIDATION_REGRESSION == "validation_regression"
    assert ReplayVerdict.VALIDATION_RECOVERY == "validation_recovery"
    assert ReplayVerdict.SECURITY_REGRESSION == "security_regression"
    assert ReplayVerdict.REPLAY_FAILED == "replay_failed"
    assert ReplayVerdict.BASELINE_UNAVAILABLE == "baseline_unavailable"
    assert ReplayVerdict.INPUT_UNAVAILABLE == "input_unavailable"
    for member in ReplayVerdict:
        assert type(member.value) is str


def test_contract_version_is_stable():
    assert REPLAY_CONTRACT_VERSION == "query_replay_v1"


def test_records_are_frozen():
    import dataclasses

    delta = RetrievalDelta()
    with pytest.raises(dataclasses.FrozenInstanceError):
        delta.changed = True


def test_result_to_payload_is_json_safe_and_uses_plain_strings():
    result = ReplayResult(
        job_id="job-1",
        verdict=ReplayVerdict.RETRIEVAL_DRIFT,
        baseline_trace_id="trace_abc",
        retrieval=RetrievalDelta(
            baseline_tables=("a", "b"), observed_tables=("a", "c"),
            added=("c",), removed=("b",), changed=True),
        validation=ValidationDelta(
            baseline_valid=True, observed_valid=True, changed=False),
        security=SecurityDelta(),
        notes=("bir not",),
    )
    payload = result.to_payload()

    # JSON'a serialize edilebilmeli (TraceRecord köprüsüyle aynı beklenti)
    json.dumps(payload)

    assert payload["version"] == "query_replay_v1"
    assert payload["job_id"] == "job-1"
    # Sinirda enum degil PLAIN STRING tasinir
    assert payload["verdict"] == "retrieval_drift"
    assert type(payload["verdict"]) is str
    assert payload["retrieval"]["added"] == ["c"]
    assert payload["retrieval"]["removed"] == ["b"]
    assert payload["notes"] == ["bir not"]


def test_result_to_payload_keeps_none_dimensions_as_null():
    result = ReplayResult(job_id="job-2", verdict=ReplayVerdict.BASELINE_UNAVAILABLE)
    payload = result.to_payload()
    assert payload["retrieval"] is None
    assert payload["validation"] is None
    assert payload["security"] is None
    assert payload["error_code"] is None
    assert payload["baseline_trace_id"] is None


def test_to_payload_is_deterministic():
    baseline = ReplayBaseline(trace_id="t1", retrieval_tables=("a", "b"))
    observed = ReplayObserved(retrieval_tables=("a", "b"))
    assert baseline.to_payload() == baseline.to_payload()
    assert observed.to_payload() == observed.to_payload()
