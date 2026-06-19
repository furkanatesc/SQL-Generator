"""Direct tests for the shared app.security._sql_text helper (used by 26.2 + 26.3)."""

from app.security._sql_text import (
    sanitize,
    normalize,
    to_executable_core,
    leading_keyword,
    PREFIX_MAX_LEN,
)


def test_sanitize_strips_line_and_block_comments():
    assert "DROP" not in sanitize("SELECT 1 -- DROP TABLE t").upper().replace("SELECT 1", "")
    assert "secret" not in sanitize("SELECT /* secret */ 1")
    # Leading comment leaves the statement starting at SELECT after normalize.
    assert to_executable_core("/* hi */ SELECT 1") == "SELECT 1"
    assert to_executable_core("-- note\nSELECT 1") == "SELECT 1"


def test_sanitize_masks_string_literals_and_quoted_identifiers():
    # Keywords/semicolons inside a literal are masked away (not executable code).
    assert ";" not in sanitize("SELECT ';' AS s")
    assert "DROP" not in sanitize("SELECT 'please DROP it'").upper()
    # Quoted identifier content is masked too.
    assert "merge" not in sanitize('SELECT * FROM "merge"').lower()


def test_sanitize_handles_doubled_quote_escapes():
    # '' is an embedded quote, not a terminator: the trailing ; stays executable.
    out = normalize(sanitize("SELECT 'it''s fine' ; DROP"))
    assert ";" in out
    assert "DROP" in out.upper()


def test_sanitize_unterminated_literal_is_masked_to_end():
    out = sanitize("SELECT 'abc ; DROP TABLE t")
    assert "DROP" not in out.upper()
    assert ";" not in out


def test_to_executable_core_strips_single_trailing_semicolon_only():
    assert to_executable_core("SELECT 1;") == "SELECT 1"
    # An embedded ; (between statements) is preserved for multi-statement detection.
    assert ";" in to_executable_core("SELECT 1; SELECT 2")


def test_leading_keyword():
    assert leading_keyword("SELECT 1") == "SELECT"
    assert leading_keyword("  with x as (select 1) select 1") == "WITH"
    assert leading_keyword("(SELECT 1)") is None  # starts with punctuation
    assert leading_keyword("") is None
    # Capped to PREFIX_MAX_LEN.
    long_kw = "a" * (PREFIX_MAX_LEN + 10)
    assert len(leading_keyword(long_kw)) == PREFIX_MAX_LEN
