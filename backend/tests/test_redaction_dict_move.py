def test_redact_sensitive_dict_importable_from_redaction():
    from app.trace.redaction import redact_sensitive_dict
    out = redact_sensitive_dict({"api_key": "secret123", "nested": {"password": "p"}})
    assert out["api_key"] == "[REDACTED]"
    assert out["nested"]["password"] == "[REDACTED]"


def test_debug_api_reexports_redact_sensitive_dict():
    # Geriye donuk uyum: eski import yolu calismaya devam eder.
    from app.trace.debug_api import redact_sensitive_dict as via_debug
    from app.trace.redaction import redact_sensitive_dict as via_redaction
    assert via_debug is via_redaction
