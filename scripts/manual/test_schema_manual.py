import os
import sys
from backend.app.schema_manager import SchemaManager

def run_load_schema_check():
    print("Testing load_schema...")
    sm = SchemaManager()
    schema = sm.load_schema(force_refresh=True)
    print("load_schema finished!")

if __name__ == "__main__":
    run_load_schema_check()
