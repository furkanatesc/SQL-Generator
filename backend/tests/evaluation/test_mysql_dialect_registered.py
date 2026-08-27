from app.evaluation.multi_database_execution import SQLDatabaseDialect


def test_mysql_dialect_member_exists():
    assert SQLDatabaseDialect.MYSQL.value == "mysql"


def test_mysql_alongside_existing_dialects():
    values = {d.value for d in SQLDatabaseDialect}
    assert {"sqlite", "postgresql", "oracle", "mysql"} <= values
