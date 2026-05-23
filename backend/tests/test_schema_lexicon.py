import pytest
from app.nlp.text_normalizer import TextNormalizer
from app.schema_lexicon import SchemaLexiconBuilder

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
    
    # "id" is generic, it cannot seed
    assert "id" in lexicon
    assert lexicon["id"]["can_seed"] is False
    assert lexicon["id"]["can_support"] is True
