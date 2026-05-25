import sqlglot
from sqlglot import exp as sqlglot_exp
from typing import Dict, Any, Tuple

from app.sql_dialects import DEFAULT_SQL_DIALECT, normalize_sql_dialect

class SQLValidator:
    """
    Katman 1: Semantik ve Sözdizimi Kontrolleri
    Tablo/kolon isimlerinin şemada var olduğunu doğrular.
    """
    
    @staticmethod
    def validate(sql: str, schema: Dict[str, Any], dialect: str = DEFAULT_SQL_DIALECT) -> Tuple[bool, str]:
        # 1. Dialect & Syntax Validasyon & AST Parsing
        try:
            dialect = normalize_sql_dialect(dialect)
        except ValueError as e:
            return False, f"DIALECT ERROR: {str(e)}"

        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception as e:
            return False, f"SYNTAX ERROR: {str(e)}"
            
        # 2. Temel tip kontrolü (Güvenlik kontrolleri artık SQLGuardrailValidator'da yapılıyor)
        if not isinstance(tree, sqlglot_exp.Select):
            return False, "SECURITY ERROR: Only SELECT statements are allowed."
            
        # 3. Şema-bazlı Tablo/Kolon Doğrulama (Semantik)
        return SQLValidator._validate_schema_references(tree, schema)
        
    @staticmethod
    def _validate_schema_references(tree, schema: Dict[str, Any]) -> Tuple[bool, str]:
        schema_tables = schema.get("tables", {})
        table_lookup = {t.upper(): t for t in schema_tables.keys()}
        
        column_lookup = {}
        for t_name, t_meta in schema_tables.items():
            column_lookup[t_name.upper()] = {
                col["name"].upper() for col in t_meta.get("columns", [])
            }

        errors = []

        # Tablo referansları
        referenced_tables = set()
        for table_node in tree.find_all(sqlglot_exp.Table):
            table_name = table_node.name.upper() if table_node.name else None
            if table_name:
                referenced_tables.add(table_name)
                if table_name not in table_lookup:
                    errors.append(f"Table '{table_name}' does not exist in the schema.")

        alias_map = {}
        for table_node in tree.find_all(sqlglot_exp.Table):
            tname = table_node.name.upper() if table_node.name else None
            talias = table_node.alias.upper() if table_node.alias else None
            if tname and talias:
                alias_map[talias] = tname
            elif tname:
                alias_map[tname] = tname

        select_aliases = set()
        for alias_node in tree.find_all(sqlglot_exp.Alias):
            if alias_node.alias:
                select_aliases.add(alias_node.alias.upper())

        # Kolon referansları
        for col_node in tree.find_all(sqlglot_exp.Column):
            col_name = col_node.name.upper() if col_node.name else None
            if not col_name or col_name == "*":
                continue

            if col_name in select_aliases:
                continue

            table_ref = col_node.table.upper() if col_node.table else None
            resolved_table = alias_map.get(table_ref, table_ref) if table_ref else None

            if resolved_table and resolved_table in column_lookup:
                if col_name not in column_lookup[resolved_table]:
                    errors.append(f"Column '{col_name}' does not exist in table '{resolved_table}'.")
            elif not resolved_table:
                found_in_any = False
                for ref_t in referenced_tables:
                    if ref_t in column_lookup and col_name in column_lookup[ref_t]:
                        found_in_any = True
                        break
                if not found_in_any and referenced_tables:
                    errors.append(f"Column '{col_name}' does not exist in any referenced table.")

        if errors:
            return False, "SEMANTIC ERROR: " + "; ".join(errors)
        return True, ""
