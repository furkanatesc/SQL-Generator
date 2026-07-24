"""app.replay saflik guard'i (Sprint 27.4 T1).

app.replay yaprak katmandir: stdlib + TEK ISTISNA disinda hicbir app.* modülü
import etmez. Istisna app.errors'tur (Sprint 27.4 merge-kapisi duzeltmesi):
olculdu — app.errors yalniz kendi alt modullerini (categories/codes/registry)
ceker, hicbir driver/framework (sqlite3, psycopg, sqlglot, fastapi, pydantic...)
yuklemez ve kendi saflik guard'ina sahiptir (test_errors_package_purity.py).
Bu yuzden app.replay'in guvenlik ekseni kararini 27.2 registry'sinin
KATEGORISINE dayandirmasi (stage yerine) bu safligi bozmaz.

app.trace ise HALA YASAKTIR: paketin __init__'i canli pipeline'in tum
bagimliliklarini eager import eder (sqlite3 + 19 app modülü — import esleme
yan etkisi), stage/status literal'leri bu yuzden app.replay icinde yerel sabit
olarak tanimlanir. Kardes guard'lar: test_feedback_package_purity.py,
test_errors_package_purity.py.

Kontrol TAZE BIR YORUMLAYICI ALT SURECINDE kosulur, sys.modules cache'inden
bagimsiz olsun diye: ayni surecte kosulan bir guard, sizan modul (ör. app.trace,
sqlite3) daha once BASKA bir test tarafindan zaten import edilmisse
"newly_loaded" kumesine hic girmez ve olcum sessizce yanlis-negatif verir. Bu
tam olarak 27.4 whole-branch review'unde olculdu: baseline_extraction.py'ye
kasten `from app.trace.end_to_end_trace import TraceStageKind` enjekte
edildiginde izole koşuda guard fail etti ama TAM SUITE yesil kaldi.
"""
import ast
import pathlib
import subprocess
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]

_ALLOWED_APP_PREFIXES = ("app.replay", "app.errors")

_PROBE = """
import sys
before = set(sys.modules)
import app.replay  # noqa: F401
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


def test_replay_package_imports_only_stdlib_and_app_errors():
    # Taze yorumlayici: sys.modules cache'i olcumu maskeleyemez. Ayni guard'i
    # ayni surecte kosmak, sizan modul baska bir testte zaten yuklendiginde
    # sessizce yesil verirdi (27.4 whole-branch review'unde olculdu).
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR))
    assert result.returncode == 0, result.stderr
    leaked_app, drivers = ast.literal_eval(result.stdout.strip())
    assert leaked_app == [], (
        f"app.replay izinsiz bir app modulu sizdirdi (yalniz app.errors "
        f"izinlidir): {leaked_app}")
    assert drivers == [], f"app.replay driver/framework yukledi: {drivers}"
