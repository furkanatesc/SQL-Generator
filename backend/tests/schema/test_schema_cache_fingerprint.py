from app.schema_cache_fingerprint import compute_cache_fingerprint, SCHEMA_CACHE_VERSION

def _fp(**over):
    base = dict(db_type="sqlite", hidden_tables_raw="[]",
               hidden_columns_raw="{}", embedding_model="m1")
    base.update(over)
    return compute_cache_fingerprint(**base)

def test_fingerprint_is_deterministic_and_hex64():
    a, b = _fp(), _fp()
    assert a == b and len(a) == 64 and all(c in "0123456789abcdef" for c in a)

def test_each_input_axis_changes_the_hash():
    base = _fp()
    assert _fp(db_type="postgres") != base
    assert _fp(hidden_tables_raw='["orders"]') != base
    assert _fp(hidden_columns_raw='{"orders": ["secret"]}') != base
    assert _fp(embedding_model="m2") != base
    assert compute_cache_fingerprint(db_type="sqlite", hidden_tables_raw="[]",
        hidden_columns_raw="{}", embedding_model="m1", cache_version="v2") != base

def test_none_inputs_normalize_to_empty_string_no_crash():
    x = compute_cache_fingerprint(db_type=None, hidden_tables_raw=None,
                                  hidden_columns_raw=None, embedding_model=None)
    assert len(x) == 64
    # None normalizes to "" — same as passing empty strings
    y = compute_cache_fingerprint(db_type="", hidden_tables_raw="",
                                  hidden_columns_raw="", embedding_model="")
    assert x == y

def test_default_cache_version_used_when_omitted():
    assert _fp() == compute_cache_fingerprint(db_type="sqlite", hidden_tables_raw="[]",
        hidden_columns_raw="{}", embedding_model="m1", cache_version=SCHEMA_CACHE_VERSION)
