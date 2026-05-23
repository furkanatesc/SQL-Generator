import pytest
from unittest.mock import patch, MagicMock
from app.synonym_repository import HybridSynonymRepository, SynonymRule
from app.nlp.text_normalizer import TextNormalizer

def test_hybrid_repository_returns_static_rules_on_db_failure():
    normalizer = TextNormalizer()
    repo = HybridSynonymRepository(normalizer=normalizer)
    
    # Mock get_db_connection to raise an exception
    with patch('app.synonym_repository.get_db_connection', side_effect=Exception("DB Down")):
        rules = repo.lookup("ver")
        
    assert len(rules) > 0
    # The static rule for "ver" should be returned
    assert any(r.target_type == "ignore" and r.target_name == "ignore:command_verb" for r in rules)

@patch('app.synonym_repository.get_db_connection')
def test_hybrid_repository_deduplicates_and_prioritizes_db_rules(mock_db_connection):
    normalizer = TextNormalizer()
    repo = HybridSynonymRepository(normalizer=normalizer)
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_db_connection.return_value = mock_conn
    
    # Static repo has 'hekim' -> 'doktor' (priority 10)
    # We add a DB rule with higher priority (lower number: 5)
    mock_cursor.fetchall.return_value = [
        {
            "term": "hekim",
            "normalized_term": "hekim",
            "target_type": "concept",
            "target_name": "doktor",
            "confidence": 0.99,
            "source": "db",
            "priority": 5
        }
    ]
    
    rules = repo.lookup("hekim")
    
    # Should only return one rule for 'hekim' -> 'doktor' due to deduplication
    doktor_rules = [r for r in rules if r.target_name == "doktor"]
    assert len(doktor_rules) == 1
    
    winning_rule = doktor_rules[0]
    # The DB rule should win because priority 5 is better than priority 10
    assert winning_rule.source == "db"
    assert winning_rule.confidence == 0.99
