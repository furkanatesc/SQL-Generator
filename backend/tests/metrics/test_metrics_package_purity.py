"""app.metrics saflik guard'i (Sprint 27.6).

app.metrics yaprak katmandir: stdlib + app.errors disinda hicbir app.* modulu
import etmez. app.errors 27.4'te olculerek izinli (yalniz kendi alt modullerini
ceker, sifir driver). app.trace YASAKTIR: paketin __init__'i tum trace paketini
(sqlite3 + 19 app modulu) eager import eder. Kardes guard'lar:
tests/replay/test_replay_package_purity.py, tests/debug_bundle/test_debug_bundle_package_purity.py.

Kontrol TAZE BIR ALT SURECTE kosulur: ayni surecte kosulan guard, sizan modul
baska bir test tarafindan zaten import edilmisse sessizce yanlis-negatif verir.
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_ALLOWED_APP_PREFIXES = ("app.metrics", "app.errors")

_PROBE = """
import sys
before = set(sys.modules)
import app.metrics  # noqa: F401
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


def test_metrics_package_imports_only_stdlib_and_app_errors():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.metrics izinsiz app modulu sizdirdi (yalniz app.errors izinli): {leaked_app}")
    assert drivers == [], f"app.metrics driver/framework yukledi: {drivers}"
