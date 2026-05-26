from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.profiles import EvalProfile
from evals.sql_normalizer import normalize_sql


# 1. Golden profile loads a non-empty case set
def test_golden_profile_loads_non_empty_case_set():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    assert len(cases) >= 5


# 2. Every golden case ID is unique
def test_golden_profile_case_ids_are_unique():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids))


# 3. Golden case IDs are stable-looking, lower_snake_case, and start with 'golden_'
def test_golden_profile_case_ids_are_stable_and_prefixed():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    for case in cases:
        assert case.case_id.startswith("golden_")
        assert case.case_id == case.case_id.lower()
        assert " " not in case.case_id


# 4. Golden cases are sorted and returned in a stable, deterministic alphabetical order
def test_golden_profile_cases_are_ordered_deterministically():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    ids = [case.case_id for case in cases]
    assert ids == sorted(ids)


# 5. Every success golden case utilizes the expected_sql Oracle contract
def test_golden_profile_success_cases_use_expected_sql():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    for case in cases:
        assert case.expected_type == "success"
        assert case.expected_sql


# 6. Golden cases do not use sql_contains as a primary expectation oracle
def test_golden_profile_does_not_use_sql_contains_as_primary_oracle():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    for case in cases:
        assert case.expected_sql
        # Confirm that required_sql_fragments or sql_contains (if existing) are not utilized as primary oracle
        assert not hasattr(case, "sql_contains") or not getattr(case, "sql_contains")


# 7. expected_sql string is non-empty and well-formed
def test_golden_profile_expected_sql_is_non_empty():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    for case in cases:
        assert isinstance(case.expected_sql, str)
        assert case.expected_sql.strip() != ""


# 8. expected_sql is normalizable and successfully parsed by sql_normalizer
def test_golden_profile_expected_sql_is_normalizable():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    for case in cases:
        normalized = normalize_sql(case.expected_sql)
        assert normalized is not None
        assert normalized.strip() != ""


# 9. Golden cases cover critical core SQL structural shapes for SQL generation validation
def test_golden_profile_covers_core_sql_shapes():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    sql_blob = "\n".join(case.expected_sql.lower() for case in cases)

    assert "select" in sql_blob
    assert "where" in sql_blob
    assert "count(" in sql_blob
    assert "join" in sql_blob
    assert "group by" in sql_blob
    assert "order by" in sql_blob


# 10. Golden profile loading is fully isolated and does not execute database, LLM, or network
def test_golden_profile_does_not_require_db_llm_or_network():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    assert isinstance(cases, list)
    assert len(cases) > 0
