"""Sprint 26.8 — Prompt-Injection / NL Abuse Defense Contract (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This is the first Phase 7 contract
that inspects **natural language** (the user's request and the content embedded into
the prompt) rather than SQL. It **detects** prompt-injection / NL-abuse and reports
*what kind* of attack, *from which source* (direct vs indirect), *with what
confidence*, plus an advisory **disposition** (ALLOW / REVIEW / BLOCK).

It is a **hybrid detector with an advisory disposition — NOT a hard gate.** A sound
gate over free-form natural language is impossible: heuristics over NL both
under-detect (novel/paraphrased attacks) and over-detect (benign text resembling an
attack). The disposition feeds downstream governance (approval 26.7, audit 26.6, the
request pipeline), which decides what to enforce.

Grounded in OWASP LLM Top 10 (2025) LLM01 Prompt Injection: direct injection (the
user's own input), indirect injection (instructions embedded in external/retrieved
content), and jailbreaking (MITRE ATLAS AML.T0054).

Secret-free: results carry NO raw input text and NO matched substring — only stable
``pattern_label`` rule ids, the matched category/source/confidence, the segment
index, and ``input_sha256``.

Out of scope (later sprints / deliberate): any *enforcement* (the pipeline wires
blocking), result-set/row privacy (26.9), credential vault (26.10), semantic/LLM-based
classification, multilingual pattern coverage beyond English, full recursive decoding
of nested encodings, denial-of-wallet / input-size limits, any I/O. This module
performs no I/O.

KNOWN LIMITATIONS (regex over normalized text; a sound fix needs an LLM-based guard
model — a later phase):

* Heuristic in BOTH directions: under-detects novel/paraphrased/translated attacks
  (no semantics) AND over-detects benign text resembling a pattern (e.g. "ignore the
  rows where status is closed"). A **signal + advisory disposition, never a gate.**
* English-centric pattern families; multilingual coverage is out of scope.
* Obfuscation is **flagged, not defeated**: zero-width / base64 / Cyrillic-Greek
  homoglyph evasion raises a signal, but nested encodings are not recursively decoded.
* Turkish-safe by design: the homoglyph check keys on Cyrillic/Greek code points, NOT
  a non-ASCII ratio, so Turkish/diacritic-Latin input is never flagged.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

PROMPT_INJECTION_DEFENSE_CONTRACT_VERSION = "prompt_injection_defense_contract_v1"


class PromptInjectionDefenseContractError(ValueError):
    """Raised when prompt-injection defense contract rules are violated."""
    pass


class InjectionCategory(str, Enum):
    INSTRUCTION_OVERRIDE = "instruction_override"
    SYSTEM_PROMPT_EXFIL = "system_prompt_exfil"
    ROLE_HIJACK = "role_hijack"
    DELIMITER_BREAKOUT = "delimiter_breakout"
    OBFUSCATION_EVASION = "obfuscation_evasion"
    SQL_ABUSE_INTENT = "sql_abuse_intent"


class InjectionSource(str, Enum):
    DIRECT = "direct"      # the user's own NL request
    INDIRECT = "indirect"  # text embedded into the prompt (schema comments, few-shot, retrieved)


class InjectionConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InjectionDisposition(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class InjectionReasonCode(str, Enum):
    NO_INJECTION_DETECTED = "no_injection_detected"   # -> ALLOW, no matches
    INJECTION_SUSPECTED = "injection_suspected"       # -> REVIEW
    INJECTION_DETECTED = "injection_detected"         # -> BLOCK
    NO_INPUT = "no_input"                             # empty/unusable -> ALLOW


_CONFIDENCE_ORDER: Dict[InjectionConfidence, int] = {
    InjectionConfidence.LOW: 0,
    InjectionConfidence.MEDIUM: 1,
    InjectionConfidence.HIGH: 2,
}

_DISPOSITION_ORDER: Dict[InjectionDisposition, int] = {
    InjectionDisposition.ALLOW: 0,
    InjectionDisposition.REVIEW: 1,
    InjectionDisposition.BLOCK: 2,
}

_SHA256_RE = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class PromptSegment:
    """One piece of text to inspect, tagged with its provenance. The user's question
    is a DIRECT segment; schema/column comments, few-shot examples, or retrieved
    context embedded into the prompt are INDIRECT segments."""
    text: str
    source: InjectionSource

    def __post_init__(self):
        if not isinstance(self.source, InjectionSource):
            raise PromptInjectionDefenseContractError("source must be an InjectionSource")
        if not isinstance(self.text, str):
            raise PromptInjectionDefenseContractError("text must be a string")


@dataclass(frozen=True)
class InjectionMatch:
    """One detection, in a stable, typed, JSON-safe, secret-free shape. ``pattern_label``
    is a rule identifier (e.g. "instruction_override/ignore_previous") — NEVER raw text
    or the matched substring."""
    category: InjectionCategory
    source: InjectionSource
    confidence: InjectionConfidence
    pattern_label: str
    segment_index: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "pattern_label": self.pattern_label,
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True)
class PromptInjectionDefenseRequest:
    """An immutable prompt-injection defense request: a list of source-tagged segments.
    A version mismatch or a non-PromptSegment item is a contract violation (raises);
    an empty segment list or all-empty segments yields a deterministic NO_INPUT result
    from ``evaluate()`` rather than raising."""
    version: str
    segments: Sequence[PromptSegment]

    def __post_init__(self):
        if self.version != PROMPT_INJECTION_DEFENSE_CONTRACT_VERSION:
            raise PromptInjectionDefenseContractError(f"Invalid request version: {self.version}")
        if isinstance(self.segments, (str, bytes)) or not isinstance(self.segments, Sequence):
            raise PromptInjectionDefenseContractError("segments must be a sequence of PromptSegment")
        for s in self.segments:
            if not isinstance(s, PromptSegment):
                raise PromptInjectionDefenseContractError("each segment must be a PromptSegment")


@dataclass(frozen=True)
class PromptInjectionDefenseResult:
    """An immutable, audit-grade, secret-free prompt-injection signal with an advisory
    disposition. Carries NO raw input text and NO matched substring — only the detected
    matches (each secret-free), the categories, the max confidence, the disposition +
    reason, ``input_sha256``, and the segment count."""
    version: str
    detected: Tuple[InjectionMatch, ...]
    categories: Tuple[InjectionCategory, ...]
    highest_confidence: Optional[InjectionConfidence]
    disposition: InjectionDisposition
    reason_code: InjectionReasonCode
    reason: str
    input_sha256: str
    segment_count: int

    def __post_init__(self):
        if self.version != PROMPT_INJECTION_DEFENSE_CONTRACT_VERSION:
            raise PromptInjectionDefenseContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.detected, tuple):
            raise PromptInjectionDefenseContractError("detected must be a tuple")
        for m in self.detected:
            if not isinstance(m, InjectionMatch):
                raise PromptInjectionDefenseContractError("each detected entry must be an InjectionMatch")
        if not isinstance(self.categories, tuple):
            raise PromptInjectionDefenseContractError("categories must be a tuple")
        for c in self.categories:
            if not isinstance(c, InjectionCategory):
                raise PromptInjectionDefenseContractError("each category must be an InjectionCategory")
        if self.highest_confidence is not None and not isinstance(self.highest_confidence, InjectionConfidence):
            raise PromptInjectionDefenseContractError("highest_confidence must be an InjectionConfidence or None")
        if not isinstance(self.disposition, InjectionDisposition):
            raise PromptInjectionDefenseContractError("disposition must be an InjectionDisposition")
        if not isinstance(self.reason_code, InjectionReasonCode):
            raise PromptInjectionDefenseContractError("reason_code must be an InjectionReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise PromptInjectionDefenseContractError("reason must be a non-empty string")
        if not isinstance(self.input_sha256, str) or not _SHA256_RE.fullmatch(self.input_sha256):
            raise PromptInjectionDefenseContractError("input_sha256 must be a lowercase SHA-256 hex digest")
        if not isinstance(self.segment_count, int) or self.segment_count < 0:
            raise PromptInjectionDefenseContractError("segment_count must be a non-negative int")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "detected": [m.to_dict() for m in self.detected],
            "categories": [c.value for c in self.categories],
            "highest_confidence": self.highest_confidence.value if self.highest_confidence is not None else None,
            "disposition": self.disposition.value,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "input_sha256": self.input_sha256,
            "segment_count": self.segment_count,
        }
