import json
import pytest
from dataclasses import FrozenInstanceError

from app.security.prompt_injection_defense import (
    PROMPT_INJECTION_DEFENSE_CONTRACT_VERSION,
    PromptInjectionDefenseContractError,
    InjectionCategory,
    InjectionSource,
    InjectionConfidence,
    InjectionDisposition,
    InjectionReasonCode,
    PromptSegment,
    InjectionMatch,
    PromptInjectionDefenseRequest,
    PromptInjectionDefenseResult,
)

VERSION = PROMPT_INJECTION_DEFENSE_CONTRACT_VERSION


def test_version_constant():
    assert VERSION == "prompt_injection_defense_contract_v1"


def test_segment_validates_source_and_text():
    seg = PromptSegment(text="hello", source=InjectionSource.DIRECT)
    assert seg.text == "hello"
    with pytest.raises(PromptInjectionDefenseContractError):
        PromptSegment(text="hi", source="direct")            # not an enum
    with pytest.raises(PromptInjectionDefenseContractError):
        PromptSegment(text=123, source=InjectionSource.DIRECT)  # text not a str


def test_segment_is_immutable():
    seg = PromptSegment(text="hi", source=InjectionSource.DIRECT)
    with pytest.raises(FrozenInstanceError):
        seg.text = "changed"


def test_match_to_dict_is_secret_free_and_json_safe():
    m = InjectionMatch(
        category=InjectionCategory.INSTRUCTION_OVERRIDE,
        source=InjectionSource.DIRECT,
        confidence=InjectionConfidence.HIGH,
        pattern_label="instruction_override/ignore_previous",
        segment_index=0,
    )
    d = m.to_dict()
    json.dumps(d)  # must not raise
    assert d == {
        "category": "instruction_override",
        "source": "direct",
        "confidence": "high",
        "pattern_label": "instruction_override/ignore_previous",
        "segment_index": 0,
    }


def test_request_version_mismatch_raises():
    with pytest.raises(PromptInjectionDefenseContractError):
        PromptInjectionDefenseRequest(version="wrong", segments=())


def test_request_rejects_non_segment_items():
    with pytest.raises(PromptInjectionDefenseContractError):
        PromptInjectionDefenseRequest(version=VERSION, segments=["just a string"])


def test_result_version_mismatch_raises():
    with pytest.raises(PromptInjectionDefenseContractError):
        PromptInjectionDefenseResult(
            version="wrong", detected=(), categories=(), highest_confidence=None,
            disposition=InjectionDisposition.ALLOW,
            reason_code=InjectionReasonCode.NO_INPUT, reason="x",
            input_sha256="0" * 64, segment_count=0,
        )


def test_result_to_dict_round_trips_json():
    res = PromptInjectionDefenseResult(
        version=VERSION, detected=(), categories=(), highest_confidence=None,
        disposition=InjectionDisposition.ALLOW,
        reason_code=InjectionReasonCode.NO_INJECTION_DETECTED, reason="clean",
        input_sha256="a" * 64, segment_count=1,
    )
    d = res.to_dict()
    json.dumps(d)
    assert d["disposition"] == "allow"
    assert d["reason_code"] == "no_injection_detected"
    assert d["highest_confidence"] is None
    assert d["input_sha256"] == "a" * 64
