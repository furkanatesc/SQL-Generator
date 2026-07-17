"""app.errors saflık guard'ı (Sprint 27.2 T1).

app.errors yaprak katmandır: stdlib dışında hiçbir şey import etmez.
Bu, app.trace'in onu import etmesini güvenli kılan şeydir (spec §3.2).
"""
import sys


def test_errors_package_imports_no_app_modules_and_no_drivers():
    for mod in [m for m in list(sys.modules) if m.startswith("app.errors")]:
        del sys.modules[mod]

    before = set(sys.modules)
    import app.errors  # noqa: F401
    newly_loaded = set(sys.modules) - before

    leaked_app = [m for m in newly_loaded
                  if m.startswith("app.") and not m.startswith("app.errors")]
    assert leaked_app == [], f"app.errors sızdırdı: {leaked_app}"

    for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle", "sqlglot",
                "sqlite3", "fastapi"):
        assert drv not in newly_loaded, f"app.errors {drv} yükledi"
