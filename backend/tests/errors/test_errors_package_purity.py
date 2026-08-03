"""app.errors saflik guard'i — TAZE ALT SURECTE (Sprint 27.11, §5.1).

app.errors yaprak katmandir: stdlib disinda hicbir app.* modulu import etmez.
Kontrol taze bir alt surecte kosar; ayni surecte kosan guard, sizan modul baska
bir test tarafindan zaten import edilmisse sessizce yanlis-negatif verir.
Referans: tests/rule_suggestions/test_rule_suggestions_package_purity.py
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_ALLOWED_APP_PREFIXES = ("app.errors",)

_PROBE = """
import sys
before = set(sys.modules)
import app.errors  # noqa: F401
newly = set(sys.modules) - before
allowed_prefixes = {allowed_prefixes!r}
leaked_app = sorted(m for m in newly if m.startswith("app.") and m != "app"
                    and not any(m == p or m.startswith(p + ".")
                                for p in allowed_prefixes))
drivers = sorted(d for d in ("psycopg", "psycopg2", "oracledb", "cx_Oracle",
                             "sqlglot", "sqlite3", "fastapi")
                 if d in newly)
print(repr((leaked_app, drivers)))
""".format(allowed_prefixes=_ALLOWED_APP_PREFIXES)


def test_errors_package_imports_only_stdlib():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.errors izinsiz app modulu sizdirdi (yalniz stdlib izinli): {leaked_app}")
    assert drivers == [], f"app.errors driver/framework yukledi: {drivers}"
