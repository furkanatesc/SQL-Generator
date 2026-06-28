from app.security._secret_pattern_scan import (
    scan_secret_patterns,
    SECRET_ASSIGNMENT_PATTERNS,
    CONNECTION_STRING_MARKER,
)


def test_clean_value_returns_empty():
    assert scan_secret_patterns("my_db_secret_ref") == ()


def test_detects_connection_string_marker():
    assert "://" in scan_secret_patterns("postgres://user:pw@host/db")


def test_detects_each_assignment_pattern():
    assert "password=" in scan_secret_patterns("PASSWORD=hunter2")  # case-insensitive
    assert "token=" in scan_secret_patterns("token=abc")
    assert "secret=" in scan_secret_patterns("x secret=y")
    assert "key=" in scan_secret_patterns("api_key=zzz")


def test_returns_marker_names_not_values():
    markers = scan_secret_patterns("password=hunter2")
    # the offending value must never appear in the output
    assert all("hunter2" not in m for m in markers)


def test_multiple_markers_all_returned():
    markers = scan_secret_patterns("postgres://u:p@h/db?password=x")
    assert "://" in markers and "password=" in markers


def test_non_str_raises():
    import pytest
    with pytest.raises(TypeError):
        scan_secret_patterns(123)  # type: ignore[arg-type]
