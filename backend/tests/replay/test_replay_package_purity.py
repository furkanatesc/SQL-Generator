"""app.replay saflik guard'i (Sprint 27.4 T1).

app.replay yaprak katmandir: stdlib + app.trace.end_to_end_trace + app.errors
disinda hicbir sey import etmez. Kardes guard'lar:
test_feedback_package_purity.py, test_errors_package_purity.py.
"""
import sys

_ALLOWED_APP_PREFIXES = ("app.replay", "app.trace.end_to_end_trace", "app.errors")


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
            and m not in ("app", "app.trace")
        ]
        assert leaked_app == [], f"app.replay sizdirdi: {leaked_app}"

        for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle", "sqlglot",
                    "fastapi", "pydantic"):
            assert drv not in newly_loaded, f"app.replay {drv} yukledi"
    finally:
        for m in [m for m in list(sys.modules) if m.startswith("app.replay")]:
            del sys.modules[m]
        sys.modules.update(saved)
