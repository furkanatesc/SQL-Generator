from dataclasses import dataclass
from typing import Protocol, Dict, Optional, Tuple
import hashlib
import json

@dataclass(frozen=True)
class EmbeddingRecord:
    """
    Metadata-rich representation of a cached/computed embedding.
    """
    id: str
    text: str
    vector: Tuple[float, ...]
    summary_version: str
    schema_hash: str
    provider_id: str
    model_id: str
    dimension: int
    created_at: float


class EmbeddingCache(Protocol):
    """
    Protocol defining the contract for embedding cache backends.
    """
    def get(self, key: str) -> Optional[EmbeddingRecord]:
        """
        Retrieves a record from cache by key. Returns None on cache miss.
        """
        ...

    def set(self, key: str, record: EmbeddingRecord) -> None:
        """
        Writes a record to cache.
        """
        ...

    def clear(self) -> None:
        """
        Clears all items in the cache.
        """
        ...


class InMemoryEmbeddingCache:
    """
    Simple in-memory implementation of the EmbeddingCache protocol.
    """
    def __init__(self):
        self._store: Dict[str, EmbeddingRecord] = {}

    def get(self, key: str) -> Optional[EmbeddingRecord]:
        return self._store.get(key)

    def set(self, key: str, record: EmbeddingRecord) -> None:
        self._store[key] = record

    def clear(self) -> None:
        self._store.clear()


def build_cache_key(
    provider_id: str,
    model_id: str,
    dimension: int,
    summary_version: str,
    schema_hash: str,
    object_id: str
) -> str:
    """
    Generates a deterministic and collision-free cache key:
    embedding:<sha256 of metadata payload JSON>
    """
    payload = {
        "provider_id": provider_id,
        "model_id": model_id,
        "dimension": dimension,
        "summary_version": summary_version,
        "schema_hash": schema_hash,
        "object_id": object_id,
    }
    payload_str = json.dumps(payload, sort_keys=True)
    hash_str = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    return f"embedding:{hash_str}"
