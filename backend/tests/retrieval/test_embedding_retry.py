from unittest.mock import patch, MagicMock
import pytest
import requests
from app.retrieval.embedding_pipeline import (
    execute_with_retry,
    EmbeddingError,
    EmbeddingRetryableError,
    EmbeddingNonRetryableError
)


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


@patch("time.sleep")
def test_requests_exception_classification(mock_sleep):
    """
    Verifies that requests HTTP status code and network errors are classified correctly:
    - HTTP 429 / 5xx -> Retryable
    - HTTP 400 / 401 / 403 -> Non-Retryable
    """
    # 1. HTTP 429 (Transient Rate Limit)
    mock_func_429 = MagicMock()
    resp_429 = requests.Response()
    resp_429.status_code = 429
    mock_func_429.side_effect = requests.exceptions.HTTPError(response=resp_429)

    with pytest.raises(EmbeddingError, match="Max attempts \\(3\\) reached"):
        execute_with_retry(mock_func_429, max_attempts=3, base_delay_ms=10)
    assert mock_func_429.call_count == 3

    # 2. HTTP 401 (Unauthorized - Non-Retryable)
    mock_func_401 = MagicMock()
    resp_401 = requests.Response()
    resp_401.status_code = 401
    mock_func_401.side_effect = requests.exceptions.HTTPError(response=resp_401)

    with pytest.raises(EmbeddingNonRetryableError, match="HTTP non-retryable error 401"):
        execute_with_retry(mock_func_401, max_attempts=3, base_delay_ms=10)
    assert mock_func_401.call_count == 1

    # 3. Connection Timeout (Retryable)
    mock_func_timeout = MagicMock()
    mock_func_timeout.side_effect = requests.exceptions.Timeout("Read timeout")

    with pytest.raises(EmbeddingError, match="Max attempts \\(3\\) reached"):
        execute_with_retry(mock_func_timeout, max_attempts=3, base_delay_ms=10)
    assert mock_func_timeout.call_count == 3
