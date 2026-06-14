import pytest
from dataclasses import FrozenInstanceError

from app.evaluation.golden_dataset_contract import (
    SQL_GOLDEN_DATASET_VERSION,
    SQLGoldenDatasetCase,
    SQLGoldenDatasetManifest,
    SQLGoldenDatasetTier,
    SQLResultComparePolicy,
    SQLAdjudicationStatus,
    SQLGoldenDatasetContractError,
)


def make_valid_case_args(**kwargs):
    default_args = {
        "case_id": "case_01",
        "question": "En çok sipariş veren müşterileri getir.",
        "dialect": "postgresql",
        "schema_snapshot_id": "snap_01",
        "fixture_ref": "fix_01",
        "gold_sql": "SELECT c.name, COUNT(*) FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.name",
        "tier": SQLGoldenDatasetTier.CORE_REGRESSION,
        "adjudication_status": SQLAdjudicationStatus.NEEDS_REVIEW,
    }
    default_args.update(kwargs)
    return default_args


def test_sql_golden_dataset_version_is_v2():
    assert SQL_GOLDEN_DATASET_VERSION == "sql_golden_dataset_v2"


def test_golden_dataset_case_is_frozen():
    args = make_valid_case_args()
    case = SQLGoldenDatasetCase(**args)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        case.case_id = "new_id"


def test_golden_dataset_manifest_is_frozen():
    manifest = SQLGoldenDatasetManifest(cases=())
    with pytest.raises((FrozenInstanceError, AttributeError)):
        manifest.cases = ()


@pytest.mark.parametrize("invalid_id", [None, "", "   "])
def test_case_rejects_empty_case_id(invalid_id):
    args = make_valid_case_args(case_id=invalid_id)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "case_id cannot be empty" in str(exc_info.value)


@pytest.mark.parametrize("invalid_question", [None, "", "   "])
def test_case_rejects_empty_question(invalid_question):
    args = make_valid_case_args(question=invalid_question)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "question cannot be empty" in str(exc_info.value)


def test_case_rejects_unsupported_dialect():
    args = make_valid_case_args(dialect="postgres")  # postgresql is supported, postgres is not
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "Unsupported dialect 'postgres'" in str(exc_info.value)


@pytest.mark.parametrize("invalid_snap_id", [None, "", "   "])
def test_case_rejects_empty_schema_snapshot_id(invalid_snap_id):
    args = make_valid_case_args(schema_snapshot_id=invalid_snap_id)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "schema_snapshot_id cannot be empty" in str(exc_info.value)


@pytest.mark.parametrize("invalid_fixture", [None, "", "   "])
def test_case_rejects_empty_fixture_ref(invalid_fixture):
    args = make_valid_case_args(fixture_ref=invalid_fixture)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "fixture_ref cannot be empty" in str(exc_info.value)


def test_case_rejects_invalid_compare_policy():
    args = make_valid_case_args(result_compare_policy="invalid_policy")
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "Invalid result_compare_policy" in str(exc_info.value)


def test_case_rejects_invalid_adjudication_status():
    args = make_valid_case_args(adjudication_status="invalid_status")
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "Invalid adjudication_status" in str(exc_info.value)


def test_case_rejects_invalid_tier():
    args = make_valid_case_args(tier="invalid_tier")
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "Invalid tier" in str(exc_info.value)


@pytest.mark.parametrize("empty_owner", [None, "", "   "])
def test_p0_canary_requires_owner(empty_owner):
    args = make_valid_case_args(tier=SQLGoldenDatasetTier.P0_CANARY, owner=empty_owner)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "P0 canary case requires an owner" in str(exc_info.value)


def test_approved_case_requires_expected_result_or_reason():
    # 1. No result and no reason -> reject
    args = make_valid_case_args(
        adjudication_status=SQLAdjudicationStatus.APPROVED,
        expected_result=None,
        no_expected_result_reason=None,
    )
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetCase(**args)
    assert "Approved case must have expected_result or a non-empty no_expected_result_reason" in str(exc_info.value)

    # 2. Only reason -> accept
    args_with_reason = make_valid_case_args(
        adjudication_status=SQLAdjudicationStatus.APPROVED,
        expected_result=None,
        no_expected_result_reason="Nondeterministic random output",
    )
    case_with_reason = SQLGoldenDatasetCase(**args_with_reason)
    assert case_with_reason.no_expected_result_reason == "Nondeterministic random output"

    # 3. Only result -> accept
    args_with_result = make_valid_case_args(
        adjudication_status=SQLAdjudicationStatus.APPROVED,
        expected_result=[{"count": 10}],
        no_expected_result_reason=None,
    )
    case_with_result = SQLGoldenDatasetCase(**args_with_result)
    assert case_with_result.expected_result == [{"count": 10}]


def test_manifest_rejects_duplicate_case_ids():
    args_1 = make_valid_case_args(case_id="case_01")
    args_2 = make_valid_case_args(case_id="case_01")
    case_1 = SQLGoldenDatasetCase(**args_1)
    case_2 = SQLGoldenDatasetCase(**args_2)
    with pytest.raises(SQLGoldenDatasetContractError) as exc_info:
        SQLGoldenDatasetManifest(cases=(case_1, case_2))
    assert "Duplicate case ID found" in str(exc_info.value)


def test_manifest_sorts_cases_deterministically():
    args_c3 = make_valid_case_args(case_id="case_03")
    args_c1 = make_valid_case_args(case_id="case_01")
    args_c2 = make_valid_case_args(case_id="case_02")
    cases = (
        SQLGoldenDatasetCase(**args_c3),
        SQLGoldenDatasetCase(**args_c1),
        SQLGoldenDatasetCase(**args_c2),
    )
    manifest = SQLGoldenDatasetManifest(cases=cases)
    assert manifest.cases[0].case_id == "case_01"
    assert manifest.cases[1].case_id == "case_02"
    assert manifest.cases[2].case_id == "case_03"


def test_alt_valid_sql_normalized_to_tuple():
    args = make_valid_case_args(alt_valid_sql=["SELECT 2", "SELECT 1"])
    case = SQLGoldenDatasetCase(**args)
    assert case.alt_valid_sql == ("SELECT 1", "SELECT 2")


def test_tags_normalized_to_tuple():
    args = make_valid_case_args(
        risk_tags=["slow", "pii"],
        operator_tags=["join"],
        pii_tags=None,
    )
    case = SQLGoldenDatasetCase(**args)
    assert case.risk_tags == ("pii", "slow")
    assert case.operator_tags == ("join",)
    assert case.pii_tags == ()
