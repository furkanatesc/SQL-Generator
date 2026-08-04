from app.schema.profiling import ProfileProbe


def test_probe_starts_empty():
    assert ProfileProbe().counts == {}


def test_probe_incr_accumulates():
    p = ProfileProbe()
    p.incr("dfs_visit")
    p.incr("dfs_visit")
    p.incr("adjacency_edge", 3)
    assert p.counts == {"dfs_visit": 2, "adjacency_edge": 3}


def test_probe_is_pure_stdlib():
    import app.schema.profiling as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ("datetime", "perf_counter", "time.time", "random"):
        assert forbidden not in src
