from app.evaluation.multi_database_execution import SQLDatabaseDialect


def test_sqlserver_dialect_member_exists():
    assert SQLDatabaseDialect.SQLSERVER.value == "sqlserver"


def test_sqlserver_alongside_existing_dialects():
    values = {d.value for d in SQLDatabaseDialect}
    assert {"sqlite", "postgresql", "oracle", "mysql", "sqlserver"} <= values
