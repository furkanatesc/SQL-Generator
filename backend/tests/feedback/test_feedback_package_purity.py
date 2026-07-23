"""app.feedback saflık guard'ı (Sprint 27.3 T1).

app.feedback yaprak katmandır: stdlib dışında hiçbir şey import etmez.
Bu, app.api ve 27.9 tüketicisinin onu FastAPI/DB yüklemeden import etmesini
güvenli kılar. Kardeş guard: test_errors_package_purity.py.
"""
import sys


def test_feedback_package_imports_no_app_modules_and_no_drivers():
    # app.feedback'i sys.modules'tan silip yeniden import ederek saflığı ölçer.
    # Orijinalleri try/finally ile geri yükle ki sonraki testler enum
    # sınıf-kimliğini korusun (test_errors_package_purity.py aynı deseni kullanır).
    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m.startswith("app.feedback")}
    for mod in saved:
        del sys.modules[mod]
    try:
        before = set(sys.modules)
        import app.feedback  # noqa: F401
        newly_loaded = set(sys.modules) - before

        leaked_app = [m for m in newly_loaded
                      if m.startswith("app.") and not m.startswith("app.feedback")]
        assert leaked_app == [], f"app.feedback sızdırdı: {leaked_app}"

        for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle", "sqlglot",
                    "sqlite3", "fastapi", "pydantic"):
            assert drv not in newly_loaded, f"app.feedback {drv} yükledi"
    finally:
        for m in [m for m in list(sys.modules) if m.startswith("app.feedback")]:
            del sys.modules[m]
        sys.modules.update(saved)
