import pytest
from unittest.mock import patch, MagicMock
from app.schema_pruner import SchemaPruner, TraversalPolicy

@pytest.fixture
def pruner():
    # RAG Manager'ı mockluyoruz ki sadece leksikal ve statik eşleşmeleri test edelim
    with patch('app.schema_pruner.NetworkXGraphBackend.build_graph'), \
         patch('app.schema_pruner.NetworkXGraphBackend.top_neighbors', return_value=[]), \
         patch('app.schema_pruner.NetworkXGraphBackend.shortest_path', return_value=[]):
        p = SchemaPruner()
        yield p

@pytest.fixture
def mock_schema():
    return {
        "tables": {
            "HST_DOKTOR": {
                "columns": [{"name": "doktor_id"}, {"name": "doktor_adi"}, {"name": "brans_kodu"}],
                "foreign_keys": []
            },
            "HST_HASTA": {
                "columns": [{"name": "hasta_id"}, {"name": "hasta_adi"}, {"name": "tc_kimlik_no"}],
                "foreign_keys": []
            },
            "PER_VERGIIADE_MAIN": {
                "columns": [{"name": "id"}, {"name": "vergi_no"}],
                "foreign_keys": []
            },
            "PER_VERILER": {
                "columns": [{"name": "id"}, {"name": "veri_tipi"}],
                "foreign_keys": []
            },
            "LOG": {
                "columns": [{"name": "log_id"}, {"name": "islem_tarihi"}],
                "foreign_keys": []
            },
            "KULLANICI": {
                "columns": [{"name": "id"}, {"name": "kullanici_adi"}],
                "foreign_keys": []
            }
        },
        "graph": {
            "edges": []
        }
    }

GOLDEN_QUERIES = [
    {
        "query": "bana kardiyoloji doktorlarını getiren sorguyu ver",
        "expected_tables": ["HST_DOKTOR"],
        "forbidden_tables": ["PER_VERGIIADE_MAIN", "PER_VERILER", "LOG", "KULLANICI"]
    },
    {
        "query": "hasta adı ahmet olan kayıtların sayısı",
        "expected_tables": ["HST_HASTA"],
        "forbidden_tables": ["LOG", "KULLANICI"]
    },
    {
        "query": "doktor branşlarını listele",
        "expected_tables": ["HST_DOKTOR"],
        "forbidden_tables": ["HST_HASTA"]
    },
    {
        "query": "personel vergi iade verilerini ver",
        "expected_tables": ["PER_VERGIIADE_MAIN", "PER_VERILER"],
        "forbidden_tables": ["HST_DOKTOR", "HST_HASTA"]
    },
    {
        "query": "tüm doktorları ve hastaları ver",
        "expected_tables": ["HST_DOKTOR", "HST_HASTA"],
        "forbidden_tables": ["PER_VERGIIADE_MAIN"]
    }
]

@patch('app.schema_pruner.SchemaManager.load_schema')
@patch('app.rag_manager.RAGManager')
def test_golden_queries(mock_rag, mock_load, pruner, mock_schema):
    mock_load.return_value = mock_schema
    
    def mock_search_ddl(query_text, limit=10):
        for case in GOLDEN_QUERIES:
            if case["query"] == query_text:
                return [{"payload": {"table_name": tbl}, "score": 0.85} for tbl in case["expected_tables"]]
        return []
        
    mock_rag_instance = MagicMock()
    mock_rag_instance.search_ddl.side_effect = mock_search_ddl
    mock_rag.return_value = mock_rag_instance
    
    policy = TraversalPolicy(min_edge_weight=0.45)
    
    for case in GOLDEN_QUERIES:
        aqr = {"natural_query": case["query"], "entities": [case["query"]]}
        
        result = pruner.prune_schema(aqr, policy=policy)
        
        assert result["pruned"] is True, f"Failed on query: {case['query']}"
        selected = set(result["tables"].keys())
        
        for expected in case["expected_tables"]:
            assert expected in selected, f"Missing expected table {expected} for query: {case['query']}"
            
        for forbidden in case["forbidden_tables"]:
            assert forbidden not in selected, f"Forbidden table {forbidden} selected for query: {case['query']}"

@patch('app.schema_pruner.SchemaManager.load_schema')
@patch('app.rag_manager.RAGManager')
def test_no_full_schema_fallback(mock_rag, mock_load, pruner, mock_schema):
    mock_load.return_value = mock_schema
    mock_rag_instance = MagicMock()
    mock_rag_instance.search_ddl.return_value = []
    mock_rag.return_value = mock_rag_instance
    
    aqr = {"natural_query": "xyzabc uzay mekikleri", "entities": ["xyzabc", "uzay", "mekikleri"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is False
    assert "error" in result
    assert result["pruned_table_count"] == 0
    assert len(result["tables"]) == 0

@patch('app.schema_pruner.SchemaManager.load_schema')
@patch('app.rag_manager.RAGManager')
def test_generic_token_snowball(mock_rag, mock_load, pruner, mock_schema):
    mock_load.return_value = mock_schema
    mock_rag_instance = MagicMock()
    mock_rag_instance.search_ddl.return_value = []
    mock_rag.return_value = mock_rag_instance
    
    aqr = {"natural_query": "aktif pasif durum kodu id no ad adi", "entities": ["aktif pasif durum kodu id no ad adi"]}
    
    result = pruner.prune_schema(aqr)
    
    # Generic tokenlar seed üretemeyeceği için tablo bulamamalı
    assert result["pruned"] is False
    assert "error" in result
    assert result["pruned_table_count"] == 0
