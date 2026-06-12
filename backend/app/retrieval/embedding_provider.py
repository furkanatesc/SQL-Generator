import hashlib
import random
from typing import Protocol, Sequence, List

class EmbeddingProvider(Protocol):
    """
    Protocol defining the contract for embedding providers.
    """
    provider_id: str
    model_id: str
    dimension: int

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """
        Embeds a sequence of texts into a list of floating-point vectors.
        """
        ...


class FakeEmbeddingProvider:
    """
    Deterministic offline embedding provider for unit/integration testing.
    Ensures same text + same dimension => same vector, and different text => different vector.
    Does not make any network calls.
    """
    def __init__(self, provider_id: str = "fake_provider", model_id: str = "fake_model", dimension: int = 1536):
        self.provider_id = provider_id
        self.model_id = model_id
        self.dimension = dimension

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # Use SHA-256 hash of the text to seed the local Random generator
            h = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(h, "big")
            rng = random.Random(seed)
            # Generate deterministic vector of size self.dimension
            embeddings.append([rng.uniform(-1.0, 1.0) for _ in range(self.dimension)])
        return embeddings
