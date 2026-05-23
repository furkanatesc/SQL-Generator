import pytest
from app.nlp.text_normalizer import TextNormalizer
from app.schema_lexicon import SchemaLexiconBuilder

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

def test_tokenize_normalizes_turkish():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("branş")
    assert "brans" in tokens
    assert len(tokens) == 1

def test_per_vergiiade_main_does_not_yield_ver():
    normalizer = TextNormalizer()
    tokens = normalizer.tokenize("PER_VERGIIADE_MAIN")
    assert "per" in tokens
    assert "vergiiade" in tokens
    assert "main" in tokens
    assert "ver" not in tokens

def test_generic_tokens_do_not_seed():
    normalizer = TextNormalizer()
    builder = SchemaLexiconBuilder(normalizer=normalizer)
    
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {
                "columns": [{"name": "doktor_id"}, {"name": "doktor_adi"}]
            }
        }
    }
    
    lexicon = builder.build_lexicon(mock_schema)
    
    # "doktor" is a normal token, it can seed
    assert "doktor" in lexicon
    assert lexicon["doktor"]["can_seed"] is True
    assert lexicon["doktor"]["can_support"] is True
    
    # "adi" and "id" are generic, they cannot seed but can support
    assert "adi" in lexicon
    assert lexicon["adi"]["can_seed"] is False
    assert lexicon["adi"]["can_support"] is True
    
    assert "id" in lexicon
    assert lexicon["id"]["can_seed"] is False
    assert lexicon["id"]["can_support"] is True
