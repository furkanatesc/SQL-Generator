import sys
import os
import json

# Add parent directory to sys.path to ensure clean local imports of app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Error: 'mcp' library not found. Please run 'pip install mcp' in your environment.", file=sys.stderr)
    sys.exit(1)

from app.sql_pipeline import SQLGenerationPipeline
from app.schema_manager import SchemaManager
from app.excel_parser import parse_excel_request
from app.database import get_config
from app.llm_client import NVIDIAClient, get_nvidia_api_key

# Initialize FastMCP Server
mcp = FastMCP("SQLGen-MCP")

def format_schema_compact(schema: dict) -> str:
    """
    Formats the schema metadata into an ultra-compact, token-efficient pseudo-DDL format.
    Saves up to 85-90% of token count compared to standard raw JSON metadata.
    Example:
      Table customers (customer_id INT PK, name VARCHAR NOT NULL, email VARCHAR)
      Table orders (order_id INT PK, customer_id INT, amount DECIMAL | FKs: customer_id -> customers.customer_id)
    """
    output = []
    tables = schema.get("tables", {})
    if not tables:
        return "No tables found in the active database schema."
        
    for table_name, details in tables.items():
        columns = []
        for col in details.get("columns", []):
            pk = " PK" if col.get("primary_key") else ""
            null = "" if col.get("nullable", True) else " NOT NULL"
            columns.append(f"{col['name']} {col['type']}{pk}{null}")
            
        fks = []
        for fk in details.get("foreign_keys", []):
            fks.append(f"{fk['column']} -> {fk['referenced_table']}.{fk['referenced_column']}")
            
        col_str = ", ".join(columns)
        fk_str = f" | FKs: {', '.join(fks)}" if fks else ""
        output.append(f"Table {table_name} ({col_str}{fk_str})")
        
    return "\n".join(output)

@mcp.tool()
def get_token_optimized_schema() -> str:
    """
    Retrieves the active database schema formatted in an ultra-compact, token-efficient pseudo-DDL syntax.
    Designed specifically to feed database structures to external LLMs (e.g., Claude, Gemini) with minimum token cost.
    """
    try:
        manager = SchemaManager()
        schema = manager.extract_schema_metadata()
        return format_schema_compact(schema)
    except Exception as e:
        return f"Error retrieving schema: {str(e)}"

@mcp.tool()
def parse_excel_request_file(excel_path: str) -> str:
    """
    Parses a user-uploaded Excel requirement file and extracts the structured Abstract Query Representation (AQR).
    Returns columns, fields, rules, and natural queries requested in the spreadsheet.

    Args:
        excel_path: The absolute file path to the uploaded Excel document.
    """
    try:
        if not os.path.exists(excel_path):
            return f"Error: Excel file not found at the specified path: {excel_path}"
            
        aqr = parse_excel_request(excel_path)
        return json.dumps(aqr, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error parsing Excel file: {str(e)}"

@mcp.tool()
def generate_validated_sql(query: str, dialect: str = "oracle") -> str:
    """
    Generates a pre-validated, AST-verified SQL query from natural language using the local Writer-Critic pipeline.
    Avoids LLM syntax errors by validating the SQL against the target database structure using sqlglot.

    Args:
        query: Natural language request (e.g., 'bölgeye göre müşterilerin sipariş sayılarını istiyorum')
        dialect: Target database SQL dialect (e.g., 'oracle', 'postgres', 'sqlite'). Default is 'oracle'.
    """
    api_key = get_config("api_key") or get_nvidia_api_key()
    
    pipeline = SQLGenerationPipeline()
    try:
        result = pipeline.run_pipeline(
            natural_query=query,
            dialect=dialect,
            api_key=api_key
        )
        if result["success"]:
            return result["generated_sql"]
        else:
            return f"SQL Generation Failed:\nError: {result['error']}\n\nAttempts Details:\n{json.dumps(result['attempts'], indent=2, ensure_ascii=False)}"
    except Exception as e:
        return f"Pipeline Execution Error: {str(e)}"

@mcp.tool()
def design_database_schema(natural_description: str, target_engine: str = "oracle") -> str:
    """
    Designs a high-quality database schema layout from a text description or data list.
    Returns tables, data types, primary keys, and foreign keys formatted in the token-efficient pseudo-DDL.

    Args:
        natural_description: A text description of the required system or columns list (e.g., 'bir e-ticaret uygulaması için sepet, sipariş ve ürün tabloları tasarımı istiyorum')
        target_engine: The target database dialect (e.g., 'oracle', 'postgres', 'sqlite')
    """
    api_key = get_config("api_key") or get_nvidia_api_key()
    if not api_key:
        return "Error: NVIDIA API Key is not configured. Please set it in your environment or application settings."
        
    client = NVIDIAClient()
    prompt = (
        "You are an expert database architect.\n"
        f"Design a high-quality database schema for the following description using {target_engine} conventions:\n\n"
        f"Description: \"{natural_description}\"\n\n"
        "Format the output strictly as a compact, token-efficient pseudo-DDL (one table per line), with no surrounding conversation or markdown text blocks:\n"
        "Table table_name (col1 type PK, col2 type NOT NULL, col3 type | FKs: col3 -> ref_table.ref_col)\n"
    )
    try:
        design = client.generate_sql(prompt, api_key=api_key)
        return design.strip()
    except Exception as e:
        return f"Error designing database schema: {str(e)}"

if __name__ == "__main__":
    # Start the MCP server using standard I/O (stdio) protocol
    mcp.run()
