import pytest
from app.schema_graph.hub_detector import HubDetector

def test_known_name_hubs():
    detector = HubDetector()
    schema = {"tables": {"KULLANICI": {}, "DOKTOR": {}}}
    hubs = detector._known_name_hubs(schema)
    assert "KULLANICI" in hubs
    assert "DOKTOR" not in hubs

def test_token_based_hubs():
    detector = HubDetector()
    schema = {"tables": {"SYS_KULLANICI": {}, "HST_HASTANE": {}, "NORMAL_TABLO": {}}}
    hubs = detector._token_hubs(schema)
    assert "SYS_KULLANICI" in hubs
    assert "HST_HASTANE" in hubs
    assert "NORMAL_TABLO" not in hubs

def test_degree_based_hubs():
    detector = HubDetector()
    edges = []
    # Hub has 20 connections
    for i in range(20):
        edges.append({"source": "HUB_TABLE", "target": f"T_{i}"})
    # Normal tables have 1 connection
    edges.append({"source": "T_1", "target": "T_2"})
    schema = {"graph": {"edges": edges}}
    
    hubs = detector._degree_hubs(schema)
    assert "HUB_TABLE" in hubs
    assert "T_1" not in hubs
    
def test_detect_hubs_integration():
    detector = HubDetector()
    edges = [{"source": "HUB_TABLE", "target": f"T_{i}"} for i in range(20)]
    schema = {
        "tables": {
            "KULLANICI": {},
            "SYS_LOG": {},
            "HUB_TABLE": {},
            "NORMAL_TABLO": {}
        },
        "graph": {"edges": edges}
    }
    
    hubs = detector.detect_hubs(schema)
    assert "KULLANICI" in hubs
    assert "SYS_LOG" in hubs
    assert "HUB_TABLE" in hubs
    assert "NORMAL_TABLO" not in hubs

def test_detect_hub_reasons():
    detector = HubDetector()
    edges = [{"source": "HUB_TABLE", "target": f"T_{i}"} for i in range(20)]
    schema = {
        "tables": {
            "KULLANICI": {},      # known_name
            "SYS_LOG": {},        # token_match
            "HUB_TABLE": {},      # degree_p95
            "NORMAL_TABLO": {}    # none
        },
        "graph": {"edges": edges}
    }
    
    reasons = detector.detect_hub_reasons(schema)
    
    assert "known_name" in reasons["KULLANICI"]
    assert "token_match" in reasons["SYS_LOG"]
    assert "degree_p95" in reasons["HUB_TABLE"]
    assert "NORMAL_TABLO" not in reasons
