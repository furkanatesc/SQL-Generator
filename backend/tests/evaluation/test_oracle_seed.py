import os
import subprocess
import sys

import app.evaluation
from app.evaluation.oracle_seed import split_statements, apply_seed, ORACLE_SEED_VERSION


def test_version_constant():
    assert ORACLE_SEED_VERSION == "v1"


def test_split_statements_basic():
    sql = "CREATE TABLE t (id NUMBER);\nINSERT INTO t VALUES (1);\n"
    assert split_statements(sql) == ("CREATE TABLE t (id NUMBER)", "INSERT INTO t VALUES (1)")


def test_split_statements_strips_line_comments_and_blanks():
    sql = "-- a comment\nCREATE TABLE t (id NUMBER);\n\n-- trailing\nINSERT INTO t VALUES (1);\n"
    assert split_statements(sql) == ("CREATE TABLE t (id NUMBER)", "INSERT INTO t VALUES (1)")


def test_split_statements_ignores_trailing_whitespace_only_tail():
    sql = "INSERT INTO t VALUES (1);   \n   \n"
    assert split_statements(sql) == ("INSERT INTO t VALUES (1)",)


def test_split_statements_on_real_seed_file():
    seed_path = os.path.join(
        os.path.dirname(app.evaluation.__file__), "..", "..",
        "tests", "fixtures", "oracle", "seed.sql",
    )
    with open(seed_path, "r", encoding="utf-8") as fh:
        stmts = split_statements(fh.read())
    assert len(stmts) == 18
    assert stmts[0].upper().startswith("CREATE TABLE CUSTOMERS")
    assert all(not s.lstrip().startswith("--") for s in stmts)


class _FakeCursor:
    def __init__(self, log):
        self._log = log
    def execute(self, sql):
        self._log.append(sql)
    def close(self):
        self._log.append("CLOSE")


class _FakeConn:
    def __init__(self):
        self.log = []
        self.committed = False
    def cursor(self):
        return _FakeCursor(self.log)
    def commit(self):
        self.committed = True


def test_apply_seed_executes_each_statement_and_commits_once():
    conn = _FakeConn()
    n = apply_seed(conn, "CREATE TABLE t (id NUMBER);\nINSERT INTO t VALUES (1);\n")
    assert n == 2
    assert conn.log[:2] == ["CREATE TABLE t (id NUMBER)", "INSERT INTO t VALUES (1)"]
    assert conn.committed is True


def test_oracle_seed_import_does_not_load_db_drivers():
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import oracle_seed\n"
        "for mod in ['oracledb', 'cx_Oracle', 'sqlalchemy']:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, res.stdout
