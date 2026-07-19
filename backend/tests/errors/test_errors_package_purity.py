"""app.errors saflık guard'ı (Sprint 27.2 T1).

app.errors yaprak katmandır: stdlib dışında hiçbir şey import etmez.
Bu, app.trace'in onu import etmesini güvenli kılan şeydir (spec §3.2).
"""
import sys


def test_errors_package_imports_no_app_modules_and_no_drivers():
    # Bu test app.errors'ı sys.modules'tan silip yeniden import ederek saflığı
    # ölçer; bu, modül nesnelerini (ve ErrorCode/ErrorCategory sınıflarını)
    # yeniden inşa eder. Orijinalleri try/finally ile geri yükle ki sonraki
    # testler sınıf-kimliğini korusun — aksi halde bir başka test dosyasındaki
    # `is ErrorCode.X` karşılaştırması collection-zamanı sınıfa karşı bozulabilir.
    # (Kardeş guard test_live_trace_assembly.py aynı deseni kullanır; commit
    # 8e53eb7'de bu tam tuzağın sebep olduğu cross-test kirlenmesi düzeltildi.)
    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m.startswith("app.errors")}
    for mod in saved:
        del sys.modules[mod]
    try:
        before = set(sys.modules)
        import app.errors  # noqa: F401
        newly_loaded = set(sys.modules) - before

        leaked_app = [m for m in newly_loaded
                      if m.startswith("app.") and not m.startswith("app.errors")]
        assert leaked_app == [], f"app.errors sızdırdı: {leaked_app}"

        for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle", "sqlglot",
                    "sqlite3", "fastapi"):
            assert drv not in newly_loaded, f"app.errors {drv} yükledi"
    finally:
        for m in [m for m in list(sys.modules) if m.startswith("app.errors")]:
            del sys.modules[m]
        sys.modules.update(saved)
