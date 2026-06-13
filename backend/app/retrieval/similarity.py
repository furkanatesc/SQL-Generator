import math
from typing import Tuple
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

def cosine_similarity(v1: Tuple[float, ...], v2: Tuple[float, ...]) -> float:
    """
    Computes deterministic cosine similarity between two floating point vectors.
    Fails fast if:
    - vector dimensions do not match
    - any vector is empty
    - any vector is a zero vector (norm close to 0)
    """
    if not v1 or not v2:
        raise EmbeddingNonRetryableError("Vectors cannot be empty for similarity calculations.")
        
    if len(v1) != len(v2):
        raise EmbeddingNonRetryableError(
            f"Dimension mismatch in similarity calculation: expected={len(v1)}, actual={len(v2)}"
        )
        
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm1 = math.sqrt(sum(x * x for x in v1))
    norm2 = math.sqrt(sum(x * x for x in v2))
    
    # zero-norm vector check (within tolerance)
    if norm1 < 1e-9 or norm2 < 1e-9:
        raise EmbeddingNonRetryableError("Zero norm vector detected in similarity calculation.")
        
    return dot_product / (norm1 * norm2)
