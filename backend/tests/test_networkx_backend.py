import pytest
from app.schema_graph.networkx_backend import NetworkXGraphBackend

def test_path_mode_affects_shortest_path():
    schema = {
        "tables": {
            "A": {"columns": [], "foreign_keys": []},
            "B": {"columns": [], "foreign_keys": []},
            "C": {"columns": [], "foreign_keys": []},
        },
        "graph": {
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ]
        }
    }

    backend = NetworkXGraphBackend()
    backend.build_graph(schema)

    assert backend.shortest_path("C", "A", mode="directed_weighted") == []
    assert backend.shortest_path("C", "A", mode="undirected_weighted") == ["C", "B", "A"]
