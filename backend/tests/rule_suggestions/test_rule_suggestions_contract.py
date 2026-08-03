import json
from app.rule_suggestions import (
    RULE_SUGGESTIONS_CONTRACT_VERSION, RuleSuggestionsReport, SuggestionWindow,
    RuleSuggestion, IneligibleSummary,
)


def _sample() -> RuleSuggestionsReport:
    return RuleSuggestionsReport(
        version=RULE_SUGGESTIONS_CONTRACT_VERSION,
        window=SuggestionWindow(created_after=None, created_before=None, feedback_count=3,
                                eligible_count=2, suggestion_count=2, truncated=False,
                                scan_cap=10000),
        suggestions=(
            RuleSuggestion(natural_query="q1", suggested_sql="SELECT 1", kind="correction",
                           categories=("wrong_filter",), support_count=2,
                           feedback_ids=("f1", "f2"), job_ids=("j1",)),
            RuleSuggestion(natural_query="q2", suggested_sql="SELECT 2", kind="confirmation",
                           categories=(), support_count=1, feedback_ids=("f3",), job_ids=("j2",)),
        ),
        by_kind={"correction": 1, "confirmation": 1},
        by_category={"wrong_filter": 2},
        ineligible=IneligibleSummary(total=1, reasons={"missing_sql": 1}),
    )


def test_to_payload_json_safe_and_shaped():
    p = _sample().to_payload()
    json.dumps(p)
    assert p["version"] == "rule_suggestions_v1"
    assert set(p.keys()) == {"version", "window", "suggestions", "by_kind",
                             "by_category", "ineligible"}
    assert p["window"]["suggestion_count"] == 2
    assert p["suggestions"][0]["kind"] == "correction"
    assert p["suggestions"][0]["categories"] == ["wrong_filter"]
    assert p["suggestions"][0]["feedback_ids"] == ["f1", "f2"]
    assert p["ineligible"] == {"total": 1, "reasons": {"missing_sql": 1}}


def test_dicts_sorted_deterministic():
    p = _sample().to_payload()
    assert list(p["by_kind"].keys()) == ["confirmation", "correction"]


def test_empty_sections_serialize():
    r = RuleSuggestionsReport(
        version=RULE_SUGGESTIONS_CONTRACT_VERSION,
        window=SuggestionWindow(None, None, 0, 0, 0, False, 10000),
        suggestions=(), by_kind={}, by_category={},
        ineligible=IneligibleSummary(total=0, reasons={}))
    p = r.to_payload()
    assert p["suggestions"] == [] and p["by_kind"] == {} and p["by_category"] == {}
    assert p["ineligible"] == {"total": 0, "reasons": {}}
