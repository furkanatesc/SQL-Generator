import logging

import pytest
from app.schema_graph.networkx_backend import NetworkXGraphBackend


def _small_schema():
    return {
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


def test_pagerank_missing_scipy_does_not_log_error(caplog):
    # scipy is not installed in this environment: networkx.pagerank falls back
    # to the scipy-backed implementation and raises ModuleNotFoundError. That
    # is an expected/optional-dependency condition, not a genuine failure, so
    # it must not be logged at ERROR level (CI log noise / false alarm).
    backend = NetworkXGraphBackend()
    backend.build_graph(_small_schema())

    with caplog.at_level(logging.DEBUG, logger="schema_graph.networkx_backend"):
        result = backend.personalized_pagerank({"A": 1.0})

    assert result == {}
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


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
