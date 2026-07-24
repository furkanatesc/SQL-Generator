"""app.replay saflik guard'i (Sprint 27.4 T1).

app.replay yaprak katmandir: YALNIZ stdlib import eder, hicbir app.* modülü
(app.trace dahil) import etmez. Stage/status literal'leri yerel sabit olarak
tanimlanir (import esleme yan etkisi: sqlite3 + 19 app modülü). Kardes guard'lar:
test_feedback_package_purity.py, test_errors_package_purity.py.

Kontrol TAZE BIR YORUMLAYICI ALT SURECINDE kosulur, sys.modules cache'inden
bagimsiz olsun diye: ayni surecte kosulan bir guard, sizan modul (ör. app.trace,
sqlite3) daha once BASKA bir test tarafindan zaten import edilmisse
"newly_loaded" kumesine hic girmez ve olcum sessizce yanlis-negatif verir. Bu
tam olarak 27.4 whole-branch review'unde olculdu: baseline_extraction.py'ye
kasten `from app.trace.end_to_end_trace import TraceStageKind` enjekte
edildiginde izole koşuda guard fail etti ama TAM SUITE yesil kaldi.
"""
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]

_PROBE = """
import sys
before = set(sys.modules)
import app.replay  # noqa: F401
newly = set(sys.modules) - before
leaked_app = sorted(m for m in newly if m.startswith("app.") and m != "app"
                    and not m.startswith("app.replay"))
drivers = sorted(d for d in ("psycopg", "psycopg2", "oracledb", "cx_Oracle",
                             "sqlglot", "sqlite3", "fastapi", "pydantic")
                 if d in newly)
print(repr((leaked_app, drivers)))
"""


def test_replay_package_imports_only_stdlib():
    # Taze yorumlayici: sys.modules cache'i olcumu maskeleyemez. Ayni guard'i
    # ayni surecte kosmak, sizan modul baska bir testte zaten yuklendiginde
    # sessizce yesil verirdi (27.4 whole-branch review'unde olculdu).
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = eval(result.stdout.strip())
    assert leaked_app == [], f"app.replay app modulu sizdirdi: {leaked_app}"
    assert drivers == [], f"app.replay driver/framework yukledi: {drivers}"
