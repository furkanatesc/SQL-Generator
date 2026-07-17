import sqlglot
from sqlglot import exp
from typing import List, Dict, Any

from app.errors import ErrorCode
from app.sql_dialects import DEFAULT_SQL_DIALECT, normalize_sql_dialect

class SQLGuardrailValidator:
    """
    Güvenlik Duvarı (Guardrail) Katmanı
    Görevi: Sadece read-only (SELECT veya CTE-based SELECT) ifadelerine izin vermek.
    DML (Data Manipulation Language) ve DDL (Data Definition Language) içeren sorguları,
    çoklu ifadeleri (multiple statements) ve boş sorguları sert bir şekilde reddeder.
    """

    FORBIDDEN_NODE_TYPES = (
        exp.Delete,
        exp.Update,
        exp.Insert,
        exp.Drop,
        exp.AlterTable,
        exp.AlterColumn,
        exp.Command,
        exp.Create,
        exp.Commit,
        exp.Rollback,
        exp.TruncateTable,
    )

    FORBIDDEN_KEYS = {
        'delete', 'update', 'insert', 'drop', 'alter', 'truncate', 'create', 
        'grant', 'revoke', 'commit', 'rollback', 'command'
    }

    DANGEROUS_FUNCTION_NAMES = {
        "pg_sleep",
        "pg_read_file",
        "pg_ls_dir",
        "dblink",
        "lo_import",
        "lo_export",
    }

    @classmethod
    def validate(cls, sql: str, dialect: str = DEFAULT_SQL_DIALECT) -> List[Dict[str, Any]]:
        errors = []

        try:
            dialect = normalize_sql_dialect(dialect)
        except ValueError as e:
            return [{
                "type": ErrorCode.UNSUPPORTED_DIALECT,
                "stage": "sql_guardrail",
                "message": str(e),
            }]

        if not sql or not sql.strip():
            return [{
                "type": ErrorCode.EMPTY_SQL,
                "stage": "sql_guardrail",
                "message": "SQL query cannot be empty",
            }]

        try:
            # sqlglot.parse returns a list of statements
            stmts = sqlglot.parse(sql, read=dialect)
            # Filter out None values that might result from trailing semicolons or comments
            valid_stmts = [s for s in stmts if s is not None]
        except Exception as e:
            return [{
                "type": ErrorCode.SQL_PARSE_ERROR,
                "stage": "sql_guardrail",
                "message": f"Failed to parse SQL: {str(e)}",
            }]

        if not valid_stmts:
            return [{
                "type": ErrorCode.EMPTY_SQL,
                "stage": "sql_guardrail",
                "message": "SQL query contains no valid statements",
            }]

        if len(valid_stmts) > 1:
            return [{
                "type": ErrorCode.MULTIPLE_STATEMENTS,
                "stage": "sql_guardrail",
                "message": "Only single statements are allowed",
            }]

        stmt = valid_stmts[0]

        # Sadece SELECT ve türevlerine (örneğin WITH kullanarak) izin veriyoruz
        if not isinstance(stmt, exp.Select):
            return [{
                "type": ErrorCode.NON_SELECT_STATEMENT,
                "stage": "sql_guardrail",
                "message": "Only read-only SELECT statements are allowed",
                "details": {
                    "reason": "statement_type_mismatch",
                    "type": type(stmt).__name__
                }
            }]

        # Statement içinde herhangi bir yasaklı DML/DDL node'u var mı kontrol et
        for node in stmt.find_all(exp.Expression):
            node_name = getattr(node, "name", None)
            node_key = node.key.lower() if hasattr(node, "key") else ""
            
            function_name = (node_name or node_key or "").lower()

            if isinstance(node, exp.Func) and function_name in cls.DANGEROUS_FUNCTION_NAMES:
                errors.append({
                    "type": ErrorCode.UNSAFE_DANGEROUS_FUNCTION,
                    "stage": "sql_guardrail",
                    "message": "Dangerous SQL function is not allowed",
                    "details": {
                        "reason": "dangerous_function_detected",
                        "function": function_name.upper(),
                    },
                })
                break
            
            if isinstance(node, cls.FORBIDDEN_NODE_TYPES) or node_key in cls.FORBIDDEN_KEYS:
                errors.append({
                    "type": ErrorCode.UNSAFE_DML_KEYWORD,
                    "stage": "sql_guardrail",
                    "message": "Only read-only SELECT statements are allowed",
                    "details": {
                        "reason": "dml_keyword_detected",
                        "keyword": node_key.upper() if node_key else type(node).__name__.upper()
                    }
                })
                # İlk yasaklı node'u bulduktan sonra devam etmeye gerek yok
                break
                
        return errors
