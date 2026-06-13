import pytest

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Network call is forbidden in embedding unit tests")
    monkeypatch.setattr("requests.sessions.Session.request", fail)
