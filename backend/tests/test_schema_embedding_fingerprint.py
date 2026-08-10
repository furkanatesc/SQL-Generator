"""_generate_table_fingerprint delegates to the pure build_table_embedding_text
and stays byte-identical to the pre-28.8 output (Sprint 28.8, Task 2)."""
from app.schema_embedding import SchemaEmbeddingIndex
from app.schema.reindex_planner import build_table_embedding_text


class _NoClient(SchemaEmbeddingIndex):
    def __init__(self):
        self.embedding_client = None  # bypass NVIDIA client for a pure-text test


def test_fingerprint_matches_pure_helper():
    meta = {"columns": [{"name": "id", "type": "INTEGER"}, {"name": "email", "type": "TEXT"}],
            "foreign_keys": [{"referenced_table": "accounts"}]}
    idx = _NoClient()
    assert idx._generate_table_fingerprint("users", meta) == \
           build_table_embedding_text("users", meta)


def test_fingerprint_known_string():
    idx = _NoClient()
    meta = {"columns": [{"name": "id", "type": "INTEGER"}], "foreign_keys": []}
    assert idx._generate_table_fingerprint("t", meta) == "Table: t | Columns: id (INTEGER)"
