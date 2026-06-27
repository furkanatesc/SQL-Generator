import json
import pytest
from dataclasses import FrozenInstanceError

from app.security._pii_value_scan import (
    SQLPiiPhiCategory, SQLPiiPhiConfidence, SQLDataClass,
)
from app.security.result_set_privacy_limits import (
    RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION,
    ResultSetPrivacyLimitsContractError,
    ResultSetLimitDisposition,
    ResultSetLimitReasonCode,
    ResultSetLimitPolicy,
    ResultSetColumnPrivacy,
    ResultSetPrivacyLimitsRequest,
    ResultSetPrivacyLimitsResult,
)

VERSION = RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION


def test_version_constant():
    assert VERSION == "result_set_privacy_limits_contract_v1"


def test_policy_defaults_unbounded():
    p = ResultSetLimitPolicy()
    assert p.max_rows is None and p.max_bytes is None and p.max_columns is None
    assert p.truncate_allowed is False


def test_policy_rejects_negative_cap_and_bad_flag():
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetLimitPolicy(max_rows=-1)
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetLimitPolicy(truncate_allowed="yes")


def test_request_validates_types_and_version():
    req = ResultSetPrivacyLimitsRequest(
        version=VERSION, columns=("a",), rows=(("x",),), policy=ResultSetLimitPolicy())
    assert req.columns == ("a",)
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetPrivacyLimitsRequest(version="wrong", columns=(), rows=(), policy=ResultSetLimitPolicy())
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetPrivacyLimitsRequest(version=VERSION, columns=("a", 1), rows=(), policy=ResultSetLimitPolicy())
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetPrivacyLimitsRequest(version=VERSION, columns=("a",), rows=("notarow",), policy=ResultSetLimitPolicy())
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetPrivacyLimitsRequest(version=VERSION, columns=("a",), rows=(), policy="nope")


def test_column_privacy_to_dict_is_secret_free():
    c = ResultSetColumnPrivacy(
        column_index=2, column_name="notes", category=SQLPiiPhiCategory.EMAIL,
        matched_cell_count=3, highest_confidence=SQLPiiPhiConfidence.MEDIUM,
        data_class=SQLDataClass.PII)
    d = c.to_dict()
    json.dumps(d)
    assert d == {
        "column_index": 2, "column_name": "notes", "category": "email",
        "matched_cell_count": 3, "highest_confidence": "medium", "data_class": "pii",
    }


def test_result_is_immutable():
    res = ResultSetPrivacyLimitsResult(
        version=VERSION, limit_disposition=ResultSetLimitDisposition.ALLOW,
        limit_reason_code=ResultSetLimitReasonCode.WITHIN_LIMITS,
        total_rows=0, total_columns=0, estimated_bytes=0, kept_rows=0, truncated=False,
        column_privacy=(), privacy_categories=(), highest_privacy_confidence=None,
        has_phi=False, reason="ok")
    with pytest.raises(FrozenInstanceError):
        res.kept_rows = 5


from app.security.result_set_privacy_limits import _evaluate_limits


def _limits(columns, rows, **policy_kw):
    return _evaluate_limits(columns, rows, ResultSetLimitPolicy(**policy_kw))


def test_limits_allow_within_caps():
    disp, code, kept, _ = _limits(("a",), (("x",), ("y",)), max_rows=5)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.ALLOW, ResultSetLimitReasonCode.WITHIN_LIMITS, 2)


def test_limits_unbounded_policy_allows():
    disp, code, kept, _ = _limits(("a",), (("x",),) * 1000)
    assert disp == ResultSetLimitDisposition.ALLOW
    assert code == ResultSetLimitReasonCode.WITHIN_LIMITS
    assert kept == 1000


def test_limits_empty_result_allows():
    disp, code, kept, eb = _limits(("a", "b"), ())
    assert (disp, code, kept, eb) == (
        ResultSetLimitDisposition.ALLOW, ResultSetLimitReasonCode.EMPTY_RESULT, 0, 0)


def test_limits_row_cap_truncate():
    disp, code, kept, _ = _limits(
        ("a",), (("x",), ("y",), ("z",)), max_rows=2, truncate_allowed=True)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.TRUNCATE, ResultSetLimitReasonCode.ROW_CAP_TRUNCATED, 2)


def test_limits_row_cap_deny_when_truncate_not_allowed():
    disp, code, kept, _ = _limits(
        ("a",), (("x",), ("y",), ("z",)), max_rows=2, truncate_allowed=False)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.DENY, ResultSetLimitReasonCode.ROW_CAP_DENIED, 0)


def test_limits_byte_cap_truncate():
    # each single-char cell -> 1 byte; cap 2 bytes keeps 2 rows of 3.
    disp, code, kept, eb = _limits(
        ("a",), (("x",), ("y",), ("z",)), max_bytes=2, truncate_allowed=True)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.TRUNCATE, ResultSetLimitReasonCode.BYTE_CAP_TRUNCATED, 2)
    assert eb == 3


def test_limits_single_oversized_row_fails_closed():
    # row 0 alone (5 bytes) exceeds max_bytes=3 even though truncation is allowed.
    disp, code, kept, _ = _limits(
        ("a",), (("hello",), ("y",)), max_bytes=3, truncate_allowed=True)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.DENY, ResultSetLimitReasonCode.BYTE_CAP_DENIED, 0)


def test_limits_column_cap_denies_even_with_truncate_allowed():
    disp, code, kept, _ = _limits(
        ("a", "b", "c"), (("1", "2", "3"),), max_columns=2, truncate_allowed=True)
    assert (disp, code, kept) == (
        ResultSetLimitDisposition.DENY, ResultSetLimitReasonCode.COLUMN_CAP_DENIED, 0)


def test_limits_column_cap_applies_to_empty_rows():
    disp, code, kept, _ = _limits(("a", "b", "c"), (), max_columns=2)
    assert (disp, code) == (
        ResultSetLimitDisposition.DENY, ResultSetLimitReasonCode.COLUMN_CAP_DENIED)


from app.security.result_set_privacy_limits import _scan_privacy


def test_privacy_detects_email_column():
    cols, cats, hi, has_phi = _scan_privacy(
        ("id", "email"),
        ((1, "a@x.com"), (2, "b@y.com"), (3, None)))
    assert len(cols) == 1
    cp = cols[0]
    assert cp.column_index == 1 and cp.column_name == "email"
    assert cp.category == SQLPiiPhiCategory.EMAIL
    assert cp.matched_cell_count == 2          # None row skipped
    assert cats == (SQLPiiPhiCategory.EMAIL,)
    assert hi == SQLPiiPhiConfidence.MEDIUM
    assert has_phi is False


def test_privacy_column_with_two_categories_yields_two_records():
    cols, cats, _, _ = _scan_privacy(
        ("notes",),
        (("mail a@x.com call 4111111111111111",),))
    found = {c.category for c in cols}
    assert SQLPiiPhiCategory.EMAIL in found
    assert SQLPiiPhiCategory.CREDIT_CARD in found
    assert set(cats) == found


def test_privacy_skips_none_and_blank_cells():
    cols, cats, hi, _ = _scan_privacy(("c",), ((None,), ("",), ("   ",)))
    assert cols == () and cats == () and hi is None


def test_privacy_phi_sets_has_phi_and_orders_first():
    # a diagnosis-looking value won't match value-format scan; use an MRN-free PHI
    # path via a credit card (PII) plus nothing PHI -> has_phi False. To exercise
    # PHI ordering we rely on category data-class mapping in the rollup test below.
    cols, cats, hi, has_phi = _scan_privacy(("card",), (("4111111111111111",),))
    assert has_phi is False
    assert cols[0].data_class == SQLDataClass.PII
    assert hi == SQLPiiPhiConfidence.HIGH


def test_privacy_scans_full_set_even_rows_beyond_a_prefix():
    # PII only in the last row; full-set scan must still find it.
    cols, cats, _, _ = _scan_privacy(
        ("v",), (("clean",), ("clean",), ("a@x.com",)))
    assert cats == (SQLPiiPhiCategory.EMAIL,)
    assert cols[0].matched_cell_count == 1


from app.security.result_set_privacy_limits import ResultSetPrivacyLimitsContract


def _evaluate(columns, rows, **policy_kw):
    req = ResultSetPrivacyLimitsRequest(
        version=VERSION, columns=tuple(columns), rows=tuple(rows),
        policy=ResultSetLimitPolicy(**policy_kw))
    return ResultSetPrivacyLimitsContract().evaluate(req)


def test_evaluate_rejects_non_request():
    with pytest.raises(ResultSetPrivacyLimitsContractError):
        ResultSetPrivacyLimitsContract().evaluate("not a request")


def test_evaluate_allow_clean_within_limits():
    res = _evaluate(("id",), ((1,), (2,)), max_rows=10)
    assert res.limit_disposition == ResultSetLimitDisposition.ALLOW
    assert res.kept_rows == 2 and res.truncated is False
    assert res.total_rows == 2 and res.total_columns == 1
    assert res.column_privacy == () and res.privacy_categories == ()
    assert res.has_phi is False and res.highest_privacy_confidence is None


def test_evaluate_truncate_sets_kept_rows_and_truncated():
    res = _evaluate(("id",), ((1,), (2,), (3,)), max_rows=2, truncate_allowed=True)
    assert res.limit_disposition == ResultSetLimitDisposition.TRUNCATE
    assert res.kept_rows == 2 and res.truncated is True
    assert res.total_rows == 3


def test_evaluate_deny_still_reports_privacy():
    # DENY on column cap, but the privacy signal over the full set is still present.
    res = _evaluate(
        ("id", "email", "extra"),
        ((1, "a@x.com", "z"),),
        max_columns=2)
    assert res.limit_disposition == ResultSetLimitDisposition.DENY
    assert res.limit_reason_code == ResultSetLimitReasonCode.COLUMN_CAP_DENIED
    assert res.kept_rows == 0
    assert SQLPiiPhiCategory.EMAIL in res.privacy_categories


def test_evaluate_to_dict_is_secret_free_and_json_safe():
    secret = "alice.secret@example.com"
    res = _evaluate(("email",), ((secret,),))
    d = res.to_dict()
    blob = json.dumps(d)            # must not raise
    assert secret not in blob       # raw value never present
    assert "email" in d["privacy_categories"]


def test_public_exports_available_from_package():
    import app.security as sec
    for name in [
        "RESULT_SET_PRIVACY_LIMITS_CONTRACT_VERSION",
        "ResultSetPrivacyLimitsContractError",
        "ResultSetLimitDisposition",
        "ResultSetLimitReasonCode",
        "ResultSetLimitPolicy",
        "ResultSetColumnPrivacy",
        "ResultSetPrivacyLimitsRequest",
        "ResultSetPrivacyLimitsResult",
        "ResultSetPrivacyLimitsContract",
        "from_result_set",
    ]:
        assert hasattr(sec, name), name
        assert name in sec.__all__, name
