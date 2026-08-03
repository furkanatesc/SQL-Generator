from datetime import datetime, timezone
from app.dashboard import bucket_timeseries, MAX_TIMESERIES_BUCKETS


def _dt(y, mo, d, h=0):
    return datetime(y, mo, d, h, 30, 0, tzinfo=timezone.utc)  # :30 -> floor testi


def _p(terminal, ms):
    return {"terminal_status": terminal, "total_duration_ms": ms}


def test_day_buckets_floor_and_aggregate():
    items = [
        (_dt(2026, 7, 31, 10), _p("completed", 10)),
        (_dt(2026, 7, 31, 14), _p("failed", 30)),
        (_dt(2026, 8, 1, 9), _p("completed", 20)),
    ]
    buckets, truncated = bucket_timeseries(items, "day")
    assert truncated is False
    b = [x.to_payload() for x in buckets]
    assert b[0]["bucket_start"] == "2026-07-31T00:00:00+00:00"   # gun basina floor
    assert b[0]["total"] == 2 and b[0]["error_count"] == 1
    assert b[0]["success_rate"] == 0.5
    assert b[1]["bucket_start"] == "2026-08-01T00:00:00+00:00"
    assert b[1]["success_rate"] == 1.0
    # artan sirali
    assert b[0]["bucket_start"] < b[1]["bucket_start"]


def test_hour_buckets_floor():
    items = [(_dt(2026, 7, 31, 10), _p("completed", 5)),
             (_dt(2026, 7, 31, 10), _p("failed", 15))]
    buckets, _ = bucket_timeseries(items, "hour")
    assert len(buckets) == 1
    assert buckets[0].bucket_start == "2026-07-31T10:00:00+00:00"
    assert buckets[0].total == 2


def test_p95_nearest_rank_and_none_when_no_durations():
    items = [(_dt(2026, 7, 31, h), _p("completed", ms))
             for h, ms in [(1, 10), (2, 20), (3, 30), (4, 40)]]
    # ayni gune duser (day) -> tek bucket, 4 sure
    buckets, _ = bucket_timeseries(items, "day")
    assert buckets[0].p95_ms == 40      # nearest-rank ceil(.95*4)=4 -> idx3
    # sure yoksa None
    b2, _ = bucket_timeseries([(_dt(2026, 7, 31), _p("completed", None))], "day")
    assert b2[0].p95_ms is None


def test_sparse_only_populated_buckets():
    items = [(_dt(2026, 7, 31), _p("completed", 1)), (_dt(2026, 8, 3), _p("completed", 1))]
    buckets, _ = bucket_timeseries(items, "day")
    assert [x.bucket_start[:10] for x in buckets] == ["2026-07-31", "2026-08-03"]  # 08-01/02 yok


def test_truncation_keeps_most_recent():
    # MAX+5 farkli gun -> en yeni MAX tutulur, truncated=True
    from datetime import timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = [(base + timedelta(days=i), _p("completed", 1)) for i in range(MAX_TIMESERIES_BUCKETS + 5)]
    buckets, truncated = bucket_timeseries(items, "day")
    assert truncated is True
    assert len(buckets) == MAX_TIMESERIES_BUCKETS
    # en yeni tutuldu: ilk 5 gun dusmus olmali
    assert buckets[0].bucket_start > base.isoformat()


def test_empty_input():
    buckets, truncated = bucket_timeseries([], "day")
    assert buckets == () and truncated is False


def test_bucket_timeseries_skips_non_datetime_created_at():
    # None/string created_at -> _floor_iso'ya gitmeden atlanmali (§8.4b)
    items = [
        (None, _p("completed", 1)),
        ("2026-08-01T00:00:00", _p("completed", 1)),
        (_dt(2026, 8, 1, 9), _p("completed", 20)),   # gecerli datetime -> bucketlanir
    ]
    buckets, truncated = bucket_timeseries(items, "day")
    assert truncated is False
    assert len(buckets) == 1
    assert buckets[0].bucket_start == "2026-08-01T00:00:00+00:00"
    assert buckets[0].total == 1
