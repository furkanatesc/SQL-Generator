import re
import sqlglot
from sqlglot import exp

class SqlSafetyValidator:
    """
    SQL Safety Validator Layer
    Ensures that any incoming query is strictly a single, read-only SELECT (or WITH ... SELECT) statement.
    Rejects DML, DDL, empty queries, multiple statements, and any forbidden write keywords.
    """

    FORBIDDEN_KEYWORDS = {
        "insert", "update", "delete", "drop", "alter", "create", 
        "truncate", "replace", "merge", "grant", "revoke", 
        "vacuum", "analyze", "pragma", "attach", "detach"
    }

    def ensure_read_only(self, sql: str) -> None:
        """
        Validates that the provided SQL query is strictly read-only and a single SELECT statement.
        Raises ValueError if the query fails any security check.
        """
        # 1. Empty query validation
        if not sql or not sql.strip():
            raise ValueError("SQL query cannot be empty")

        # 2. Syntax and AST Parsing Validation
        parse_error = None
        try:
            # sqlglot.parse parses all statements in the query
            statements = sqlglot.parse(sql)
            valid_stmts = [s for s in statements if s is not None]
        except Exception as e:
            parse_error = e
            valid_stmts = []

        # 3. Running AST Checks if parsing was successful
        if not parse_error:
            if not valid_stmts:
                raise ValueError("SQL query contains no valid statements")

            # Multiple statement injection check
            if len(valid_stmts) > 1:
                raise ValueError("Only single statements are allowed")

            stmt = valid_stmts[0]

            # 4. Read-only SELECT class validation (also allows WITH/CTE query structures)
            if not isinstance(stmt, exp.Select):
                raise ValueError("Only read-only SELECT statements are allowed")

            # 5. AST Traversal check for any forbidden node types/keywords
            for node in stmt.find_all(exp.Expression):
                node_key = node.key.lower() if hasattr(node, "key") else ""
                if node_key in self.FORBIDDEN_KEYWORDS:
                    raise ValueError(f"Write operation detected: {node_key.upper()}")

                node_class = type(node).__name__.lower()
                for keyword in self.FORBIDDEN_KEYWORDS:
                    if keyword in node_class:
                        raise ValueError(f"Write operation detected in AST node: {node_class.upper()}")

        # 6. String-level Tokenizer bypass prevention (always executed)
        clean_sql = self._strip_comments(sql).strip().lower()
        
        # Strip single-quoted string literals and double-quoted identifiers to prevent false positives on data values
        clean_sql = re.sub(r"'.*?'", "", clean_sql)
        clean_sql = re.sub(r'".*?"', "", clean_sql)
        
        # Tokenize using word boundary boundaries to find independent keywords
        tokens = re.findall(r"\b\w+\b", clean_sql)
        for token in tokens:
            if token in self.FORBIDDEN_KEYWORDS:
                raise ValueError(f"Write keyword detected in SQL: {token.upper()}")

        # 7. Propagate parser exceptions if parsing failed and no safety keyword was present
        if parse_error:
            raise parse_error

    def _strip_comments(self, sql: str) -> str:
        """
        Strips SQL comments from the raw query string.
        """
        # Remove line comments (e.g. -- comment)
        sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
        # Remove block comments (e.g. /* comment */)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql
