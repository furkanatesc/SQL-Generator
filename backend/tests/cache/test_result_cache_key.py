from app.cache.result_cache_key import (
    RESULT_CACHE_KEY_VERSION, normalize_query, compute_result_cache_key,
)


def test_normalize_casefold_and_whitespace():
    assert normalize_query("  Show   ALL Users ") == "show all users"
    assert normalize_query("Show all users") == "show all users"
    assert normalize_query(None) == ""


def test_key_is_deterministic():
    a = compute_result_cache_key("list doctors", "postgres", "SIG")
    assert a == compute_result_cache_key("list doctors", "postgres", "SIG")


def test_key_normalization_equivalent_queries_match():
    assert compute_result_cache_key("List   Doctors", "postgres", "SIG") == \
           compute_result_cache_key("list doctors", "postgres", "SIG")


def test_key_changes_with_dialect():
    assert compute_result_cache_key("q", "postgres", "SIG") != \
           compute_result_cache_key("q", "oracle", "SIG")


def test_key_changes_with_schema_signature():
    assert compute_result_cache_key("q", "postgres", "SIG_A") != \
           compute_result_cache_key("q", "postgres", "SIG_B")


def test_key_changes_with_query():
    assert compute_result_cache_key("q1", "postgres", "SIG") != \
           compute_result_cache_key("q2", "postgres", "SIG")


def test_key_changes_with_version():
    assert compute_result_cache_key("q", "postgres", "SIG", version="v1") != \
           compute_result_cache_key("q", "postgres", "SIG", version="v2")


def test_none_dialect_and_signature_are_stable():
    assert compute_result_cache_key("q", None, None) == compute_result_cache_key("q", "", "")


def test_version_constant():
    assert RESULT_CACHE_KEY_VERSION == "v1"
