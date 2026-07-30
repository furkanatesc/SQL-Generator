"""app.debug_bundle saflik guard'i (Sprint 27.5).

app.debug_bundle yaprak katmandir: stdlib + app.replay + app.errors disinda
hicbir app.* modulu import etmez. app.trace YASAKTIR: paketin __init__'i sqlite3
+ tum trace paketini eager import eder; bu yuzden metin redaksiyonu saf katmanda
DEGIL kirli adaptorde yapilir ve compose_bundle zaten-redakte payload alir.
Kardes guard: tests/replay/test_replay_package_purity.py.

Kontrol TAZE BIR ALT SURECTE kosulur: ayni surecte kosulan guard, sizan modul
baska bir test tarafindan zaten import edilmisse sessizce yanlis-negatif verir.
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_ALLOWED_APP_PREFIXES = ("app.debug_bundle", "app.replay", "app.errors")

_PROBE = """
import sys
before = set(sys.modules)
import app.debug_bundle  # noqa: F401
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


def test_debug_bundle_imports_only_stdlib_replay_errors():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.debug_bundle izinsiz app modulu sizdirdi (yalniz app.replay/"
        f"app.errors izinli): {leaked_app}")
    assert drivers == [], f"app.debug_bundle driver/framework yukledi: {drivers}"
