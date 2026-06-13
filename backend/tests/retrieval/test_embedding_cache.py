import time
from app.retrieval.embedding_hash import compute_summary_hash
from app.retrieval.embedding_cache import InMemoryEmbeddingCache, build_cache_key, EmbeddingRecord


def test_hash_determinism():
    """
    Verifies that hash generation is byte-for-byte deterministic
    and changes appropriately when content or version changes.
    """
    summary_text = "TABLE customers\nCOLUMNS:\n- id INTEGER pk\nVERSION: schema_summary_v1"
    version = "schema_summary_v1"

    # Same summary and version must yield the exact same hash
    hash_1 = compute_summary_hash(summary_text, version)
    hash_2 = compute_summary_hash(summary_text, version)
    assert hash_1 == hash_2

    # Modified summary text must yield a different hash
    summary_text_modified = summary_text + "\n- email VARCHAR"
    hash_modified = compute_summary_hash(summary_text_modified, version)
    assert hash_1 != hash_modified

    # Modified version must yield a different hash
    hash_ver_modified = compute_summary_hash(summary_text, "schema_summary_v2")
    assert hash_1 != hash_ver_modified


def test_cache_key_determinism():
    """
    Verifies that changing any component of the cache key signature
    properly alters the key output to prevent collisions.
    """
    base_key = build_cache_key(
        provider_id="nvidia",
        model_id="embed-model-1b",
        dimension=1024,
        summary_version="schema_summary_v1",
        schema_hash="abc123hash",
        object_id="customers"
    )

    # Key must be of format embedding:<sha256_hash>
    assert base_key.startswith("embedding:")
    assert len(base_key) == 10 + 64

    # 1. Changing provider_id must change key
    key_prov = build_cache_key("openai", "embed-model-1b", 1024, "schema_summary_v1", "abc123hash", "customers")
    assert base_key != key_prov

    # 2. Changing model_id must change key
    key_model = build_cache_key("nvidia", "embed-model-2b", 1024, "schema_summary_v1", "abc123hash", "customers")
    assert base_key != key_model

    # 3. Changing dimension must change key
    key_dim = build_cache_key("nvidia", "embed-model-1b", 512, "schema_summary_v1", "abc123hash", "customers")
    assert base_key != key_dim

    # 4. Changing version must change key
    key_ver = build_cache_key("nvidia", "embed-model-1b", 1024, "schema_summary_v2", "abc123hash", "customers")
    assert base_key != key_ver

    # 5. Changing hash must change key
    key_hash = build_cache_key("nvidia", "embed-model-1b", 1024, "schema_summary_v1", "def456hash", "customers")
    assert base_key != key_hash

    # 6. Changing object_id must change key
    key_obj = build_cache_key("nvidia", "embed-model-1b", 1024, "schema_summary_v1", "abc123hash", "orders")
    assert base_key != key_obj


def test_cache_read_write_clear():
    """
    Verifies memory cache basic operations: set, get, clear.
    """
    cache = InMemoryEmbeddingCache()
    key = "embedding:testkey"
    
    record = EmbeddingRecord(
        id="table:customers",
        text="summary text",
        vector=(0.1, 0.2, 0.3),
        summary_version="schema_summary_v1",
        schema_hash="hash",
        provider_id="test",
        model_id="model",
        dimension=3,
        created_at=time.time()
    )

    # Cache get before set should return None
    assert cache.get(key) is None

    # Set and get
    cache.set(key, record)
    cached = cache.get(key)
    assert cached is not None
    assert cached.id == "table:customers"
    assert cached.vector == (0.1, 0.2, 0.3)
    assert isinstance(cached.vector, tuple)

    # Clear and verify empty
    cache.clear()
    assert cache.get(key) is None
