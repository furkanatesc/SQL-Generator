from unittest.mock import patch, MagicMock
import pytest
import requests
from app.retrieval.embedding_pipeline import (
    execute_with_retry,
    EmbeddingError,
    EmbeddingRetryableError,
    EmbeddingNonRetryableError
)
from app.retrieval.nvidia_embedding_provider import NVIDIAEmbeddingProvider


@patch("time.sleep")
def test_retry_on_transient_failures(mock_sleep):
    """
    Verifies that execute_with_retry retries on transient (retryable) errors
    and succeeds if a later attempt is successful.
    """
    mock_func = MagicMock()
    mock_func.side_effect = [
        EmbeddingRetryableError("Transient Timeout"),
        EmbeddingRetryableError("Transient Rate Limit"),
        "success_result"
    ]

    result = execute_with_retry(mock_func, max_attempts=3, base_delay_ms=10)

    assert result == "success_result"
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep")
def test_no_retry_on_permanent_failures(mock_sleep):
    """
    Verifies that permanent (non-retryable) errors fail immediately on first attempt.
    """
    mock_func = MagicMock()
    mock_func.side_effect = EmbeddingNonRetryableError("Invalid Request Parameters")

    with pytest.raises(EmbeddingNonRetryableError, match="Invalid Request Parameters"):
        execute_with_retry(mock_func, max_attempts=3, base_delay_ms=10)

    assert mock_func.call_count == 1
    assert mock_sleep.call_count == 0


@patch("time.sleep")
def test_max_attempts_exhausted(mock_sleep):
    """
    Verifies that execute_with_retry raises an EmbeddingError when all retry attempts
    fail with transient errors.
    """
    mock_func = MagicMock()
    mock_func.side_effect = EmbeddingRetryableError("Connection Timeout")

    with pytest.raises(EmbeddingError, match="Max attempts \\(3\\) reached"):
        execute_with_retry(mock_func, max_attempts=3, base_delay_ms=10)

    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2


def test_unexpected_exception_fails_fast():
    """
    Verifies that execute_with_retry wraps any unexpected raw Exception in
    EmbeddingNonRetryableError and fails fast without retrying.
    """
    mock_func = MagicMock()
    mock_func.side_effect = ValueError("Some unexpected error")

    with pytest.raises(EmbeddingNonRetryableError, match="Unexpected error during execution: Some unexpected error"):
        execute_with_retry(mock_func, max_attempts=3, base_delay_ms=10)

    assert mock_func.call_count == 1


@patch("app.rag_manager.NVIDIAEmbeddingClient")
def test_nvidia_provider_exception_classification(mock_client_cls):
    """
    Verifies that NVIDIAEmbeddingProvider correctly classifies network/HTTP exceptions
    raised by its client into EmbeddingRetryableError or EmbeddingNonRetryableError.
    """
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    
    provider = NVIDIAEmbeddingProvider(api_key="fake")

    # 1. Requests Timeout -> EmbeddingRetryableError
    mock_client.get_embeddings_batch.side_effect = requests.exceptions.Timeout("Read timeout")
    with pytest.raises(EmbeddingRetryableError, match="NVIDIA API timeout"):
        provider.embed_texts(["hello"])

    # 2. HTTP 429 -> EmbeddingRetryableError
    resp_429 = requests.Response()
    resp_429.status_code = 429
    mock_client.get_embeddings_batch.side_effect = requests.exceptions.HTTPError(response=resp_429)
    with pytest.raises(EmbeddingRetryableError, match="NVIDIA HTTP transient error 429"):
        provider.embed_texts(["hello"])

    # 3. HTTP 500 -> EmbeddingRetryableError
    resp_500 = requests.Response()
    resp_500.status_code = 500
    mock_client.get_embeddings_batch.side_effect = requests.exceptions.HTTPError(response=resp_500)
    with pytest.raises(EmbeddingRetryableError, match="NVIDIA HTTP transient error 500"):
        provider.embed_texts(["hello"])

    # 4. HTTP 401 -> EmbeddingNonRetryableError
    resp_401 = requests.Response()
    resp_401.status_code = 401
    mock_client.get_embeddings_batch.side_effect = requests.exceptions.HTTPError(response=resp_401)
    with pytest.raises(EmbeddingNonRetryableError, match="NVIDIA HTTP non-retryable error 401"):
        provider.embed_texts(["hello"])

    # 5. Generic request exception -> EmbeddingRetryableError
    mock_client.get_embeddings_batch.side_effect = requests.exceptions.RequestException("Network down")
    with pytest.raises(EmbeddingRetryableError, match="NVIDIA network error"):
        provider.embed_texts(["hello"])
