import os
import sys
from backend.app.schema_manager import SchemaManager

def test_load_schema():
    print("Testing load_schema...")
    sm = SchemaManager()
    schema = sm.load_schema(force_refresh=True)
    print("load_schema finished!")

if __name__ == "__main__":
    test_load_schema()
