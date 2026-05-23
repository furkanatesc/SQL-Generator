import pytest
from app.nlp.text_normalizer import TextNormalizer

def test_tokenize_splits_camel_case():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("doktorAdi")
    assert "doktor" in tokens
    assert "adi" in tokens
    assert len(tokens) == 2

def test_tokenize_splits_underscore():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("HST_DOKTOR")
    assert "hst" in tokens
    assert "doktor" in tokens
    assert len(tokens) == 2

def test_per_vergiiade_main_no_ver_token():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("PER_VERGIIADE_MAIN")
    assert "ver" not in tokens

def test_tokenize_normalizes_turkish():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("branş")
    assert "brans" in tokens

def test_generic_tokens_identification():
    normalizer = TextNormalizer()
    assert normalizer.is_generic("id") is True
    assert normalizer.is_generic("ad") is True
    assert normalizer.is_generic("adi") is True
    assert normalizer.is_generic("kod") is True
    assert normalizer.is_generic("doktor") is False
