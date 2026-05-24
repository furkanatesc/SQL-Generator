import sqlglot
from sqlglot import exp
from typing import List, Dict, Any

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

    @classmethod
    def validate(cls, sql: str, dialect: str = "postgres") -> List[Dict[str, Any]]:
        errors = []

        if not sql or not sql.strip():
            return [{
                "type": "empty_sql",
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
                "type": "sql_parse_error",
                "stage": "sql_guardrail",
                "message": f"Failed to parse SQL: {str(e)}",
            }]

        if not valid_stmts:
            return [{
                "type": "empty_sql",
                "stage": "sql_guardrail",
                "message": "SQL query contains no valid statements",
            }]

        if len(valid_stmts) > 1:
            return [{
                "type": "multiple_statements",
                "stage": "sql_guardrail",
                "message": "Only single statements are allowed",
            }]

        stmt = valid_stmts[0]

        # Sadece SELECT ve türevlerine (örneğin WITH kullanarak) izin veriyoruz
        if not isinstance(stmt, exp.Select):
            return [{
                "type": "non_select_statement",
                "stage": "sql_guardrail",
                "message": "Only read-only SELECT statements are allowed",
                "details": {
                    "reason": "statement_type_mismatch",
                    "type": type(stmt).__name__
                }
            }]

        # Statement içinde herhangi bir yasaklı DML/DDL node'u var mı kontrol et
        for node in stmt.find_all(exp.Expression):
            node_key = node.key.lower() if hasattr(node, "key") else ""
            
            if isinstance(node, cls.FORBIDDEN_NODE_TYPES) or node_key in cls.FORBIDDEN_KEYS:
                errors.append({
                    "type": "unsafe_sql",
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
