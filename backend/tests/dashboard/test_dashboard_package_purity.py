"""app.dashboard saflik guard'i (Sprint 27.7).

app.dashboard yaprak katmandir: stdlib + app.errors + app.metrics disinda hicbir
app.* modulu import etmez. app.metrics 27.6'da saf leaf (yalniz stdlib+app.errors);
compose_dashboard onun compute_metrics'ini reuse eder. app.trace YASAKTIR (paketin
__init__'i tum trace paketini eager import eder). Kardes guard'lar:
tests/metrics/test_metrics_package_purity.py, tests/replay/test_replay_package_purity.py.

Kontrol TAZE BIR ALT SURECTE kosulur: ayni surecte kosulan guard, sizan modul baska
bir test tarafindan zaten import edilmisse sessizce yanlis-negatif verir.
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_ALLOWED_APP_PREFIXES = ("app.dashboard", "app.metrics", "app.errors")

_PROBE = """
import sys
before = set(sys.modules)
import app.dashboard  # noqa: F401
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


def test_dashboard_package_imports_only_stdlib_errors_metrics():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.dashboard izinsiz app modulu sizdirdi (yalniz app.errors/app.metrics "
        f"izinli): {leaked_app}")
    assert drivers == [], f"app.dashboard driver/framework yukledi: {drivers}"
