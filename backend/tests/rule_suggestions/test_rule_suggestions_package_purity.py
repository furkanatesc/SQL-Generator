"""app.rule_suggestions saflik guard'i (Sprint 27.9).

app.rule_suggestions yaprak katmandir: stdlib disinda hicbir app.* modulu import
etmez (category/verdict sinirdan plain string gecer; app.feedback bile yok).
app.trace YASAKTIR. Kardes guard'lar: tests/metrics/..., tests/dashboard/...,
tests/llm_usage/...

Kontrol TAZE BIR ALT SURECTE kosulur: ayni surecte kosulan guard, sizan modul baska
bir test tarafindan zaten import edilmisse sessizce yanlis-negatif verir.
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_ALLOWED_APP_PREFIXES = ("app.rule_suggestions",)

_PROBE = """
import sys
before = set(sys.modules)
import app.rule_suggestions  # noqa: F401
newly = set(sys.modules) - before
allowed_prefixes = {allowed_prefixes!r}
leaked_app = sorted(m for m in newly if m.startswith("app.") and m != "app"
                    and not any(m == p or m.startswith(p + ".")
                                for p in allowed_prefixes))
drivers = sorted(d for d in ("psycopg", "psycopg2", "oracledb", "cx_Oracle",
                             "sqlglot", "sqlite3", "fastapi", "pydantic")
                 if d in newly)
print(repr((leaked_app, drivers)))
""".format(allowed_prefixes=_ALLOWED_APP_PREFIXES)


def test_rule_suggestions_package_imports_only_stdlib():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.rule_suggestions izinsiz app modulu sizdirdi (yalniz stdlib izinli): {leaked_app}")
    assert drivers == [], f"app.rule_suggestions driver/framework yukledi: {drivers}"
