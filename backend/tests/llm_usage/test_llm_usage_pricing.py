from app.llm_usage.pricing import parse_price_table, cost_for, DEFAULT_CURRENCY


def test_parse_valid_table():
    raw = ('{"currency":"EUR","models":{"m1":{"input_per_1m":3.0,"output_per_1m":6.0}}}')
    currency, table = parse_price_table(raw)
    assert currency == "EUR"
    assert table == {"m1": {"input_per_1m": 3.0, "output_per_1m": 6.0}}


def test_parse_none_and_invalid_json():
    assert parse_price_table(None) == (DEFAULT_CURRENCY, {})
    assert parse_price_table("") == (DEFAULT_CURRENCY, {})
    assert parse_price_table("{not json") == (DEFAULT_CURRENCY, {})
    assert parse_price_table("[1,2,3]") == (DEFAULT_CURRENCY, {})  # dict degil


def test_parse_missing_currency_defaults_usd():
    currency, table = parse_price_table('{"models":{"m1":{"input_per_1m":1,"output_per_1m":2}}}')
    assert currency == "USD"
    assert table["m1"] == {"input_per_1m": 1.0, "output_per_1m": 2.0}


def test_parse_skips_non_numeric_or_incomplete_prices():
    raw = ('{"models":{"good":{"input_per_1m":1,"output_per_1m":2},'
           '"bad1":{"input_per_1m":"x","output_per_1m":2},'
           '"bad2":{"input_per_1m":1},'
           '"bad3":"nope"}}')
    _, table = parse_price_table(raw)
    assert set(table.keys()) == {"good"}


def test_cost_for():
    price = {"input_per_1m": 3.0, "output_per_1m": 6.0}
    # 1_000_000 prompt * 3/1e6 = 3.0 ; 500_000 completion * 6/1e6 = 3.0
    assert cost_for(1_000_000, 500_000, price) == 6.0
    assert cost_for(None, None, price) == 0.0     # None token -> 0
    assert cost_for(100, 100, None) is None        # fiyat yok -> None
