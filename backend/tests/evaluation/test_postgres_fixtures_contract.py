import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SEED = os.path.join(_ROOT, "backend", "tests", "fixtures", "postgres", "seed.sql")
_COMPOSE = os.path.join(_ROOT, "docker-compose.yml")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_seed_sql_exists_and_defines_three_tables():
    assert os.path.exists(_SEED)
    sql = _read(_SEED).lower()
    for t in ("customers", "orders", "order_items"):
        assert f"create table" in sql and t in sql
    # idempotent: drops before create
    assert "drop table if exists" in sql
    # foreign keys wired
    assert "references customers" in sql
    assert "references orders" in sql


def test_compose_exists_and_matches_ci_service():
    assert os.path.exists(_COMPOSE)
    compose = _read(_COMPOSE)
    assert "postgres:16-alpine" in compose
    assert "POSTGRES_USER: sqlgen" in compose
    assert "POSTGRES_PASSWORD: sqlgen" in compose
    assert "POSTGRES_DB: sqlgen_test" in compose
    assert "5432:5432" in compose
    # seed mounted as init script
    assert "docker-entrypoint-initdb.d" in compose
    assert "seed.sql" in compose
