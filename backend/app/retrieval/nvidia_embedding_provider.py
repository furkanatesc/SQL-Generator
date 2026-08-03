from typing import Sequence, List
from app.retrieval.embedding_pipeline import EmbeddingRetryableError, EmbeddingNonRetryableError

class NVIDIAEmbeddingProvider:
    """
    Adapter around the existing NVIDIAEmbeddingClient to fit the EmbeddingProvider interface.
    """
    def __init__(self, api_key: str = None, model_id: str = "nvidia/llama-nemotron-embed-1b-v2", dimension: int = 2048):  # Nemotron gömü boyutu (rag_manager ile hizalı)
        from app.rag_manager import NVIDIAEmbeddingClient
        self.provider_id = "nvidia"
        self.model_id = model_id
        self.dimension = dimension
        self.client = NVIDIAEmbeddingClient(api_key=api_key)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        import requests
        try:
            return self.client.get_embeddings_batch(list(texts))
        except Exception as e:
            if isinstance(e, requests.exceptions.Timeout):
                raise EmbeddingRetryableError(f"NVIDIA API timeout: {e}") from e
            if isinstance(e, requests.exceptions.HTTPError):
                status_code = e.response.status_code if e.response is not None else 500
                if status_code == 429 or 500 <= status_code < 600:
                    raise EmbeddingRetryableError(f"NVIDIA HTTP transient error {status_code}: {e}") from e
                raise EmbeddingNonRetryableError(f"NVIDIA HTTP non-retryable error {status_code}: {e}") from e
            if isinstance(e, requests.exceptions.RequestException):
                raise EmbeddingRetryableError(f"NVIDIA network error: {e}") from e
            
            # Fallback text checking for standard errors
            err_msg = str(e).lower()
            if any(term in err_msg for term in ["timeout", "rate limit", "too many requests", "500", "503"]):
                raise EmbeddingRetryableError(f"NVIDIA transient error: {e}") from e
            
            raise EmbeddingNonRetryableError(f"NVIDIA non-retryable error: {e}") from e
