"""app.replay saflik guard'i (Sprint 27.4 T1).

app.replay yaprak katmandir: YALNIZ stdlib import eder, hicbir app.* modülü
(app.trace dahil) import etmez. Stage/status literal'leri yerel sabit olarak
tanimlanir (import esleme yan etkisi: sqlite3 + 19 app modülü). Kardes guard'lar:
test_feedback_package_purity.py, test_errors_package_purity.py.
"""
import sys

_ALLOWED_APP_PREFIXES = ("app.replay",)


def test_replay_package_imports_no_unexpected_app_modules_and_no_drivers():
    saved = {m: sys.modules[m] for m in list(sys.modules)
             if m.startswith("app.replay")}
    for mod in saved:
        del sys.modules[mod]
    try:
        before = set(sys.modules)
        import app.replay  # noqa: F401
        newly_loaded = set(sys.modules) - before

        leaked_app = [
            m for m in newly_loaded
            if m.startswith("app.")
            and not any(m == p or m.startswith(p + ".") for p in _ALLOWED_APP_PREFIXES)
            and m != "app"
        ]
        assert leaked_app == [], f"app.replay sizdirdi: {leaked_app}"

        for drv in ("sqlite3", "psycopg", "psycopg2", "oracledb", "cx_Oracle", "sqlglot",
                    "fastapi", "pydantic"):
            assert drv not in newly_loaded, f"app.replay {drv} yukledi"
    finally:
        for m in [m for m in list(sys.modules) if m.startswith("app.replay")]:
            del sys.modules[m]
        sys.modules.update(saved)
