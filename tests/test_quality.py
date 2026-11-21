import time

from quality import load_checks, run_checks

EXPECTED_CHECKS = {
    "ohlc_consistency",
    "zero_volume",
    "missing_trading_days",
    "stale_symbols",
    "unexplained_price_jumps",
    "invalid_corporate_actions",
    "backfill_not_completed",
}


def seed_security(conn, symbol):
    conn.execute("INSERT INTO securities (symbol, name) VALUES (?, ?)", (symbol, symbol))


def insert_price(conn, symbol, date, o, h, l, c, v=1000):
    conn.execute(
        "INSERT INTO daily_prices (symbol, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, date, o, h, l, c, v),
    )


def test_all_named_checks_are_parsed():
    assert set(load_checks().keys()) == EXPECTED_CHECKS


def test_all_checks_run_clean_against_an_empty_db(conn):
    # A smoke test that every check is valid SQL and vacuously passes with no
    # data -- guards against a syntax error or a planner trap (see
    # stale_symbols' O(n^2) bug) going unnoticed in an unused check.
    results = run_checks(conn)
    assert results.keys() == EXPECTED_CHECKS
    for name, (_, rows) in results.items():
        assert rows == [], f"{name} should have no findings on an empty db"


def test_ohlc_consistency_catches_high_below_low(conn):
    seed_security(conn, "AAPL")
    insert_price(conn, "AAPL", "2024-01-02", 10, 1, 100, 10)  # high < low

    _, rows = run_checks(conn)["ohlc_consistency"]
    assert len(rows) == 1


def test_zero_volume_is_flagged(conn):
    seed_security(conn, "AAPL")
    insert_price(conn, "AAPL", "2024-01-02", 10, 11, 9, 10.5, v=0)

    _, rows = run_checks(conn)["zero_volume"]
    assert len(rows) == 1


def test_missing_trading_days_catches_gap_inside_range(conn):
    seed_security(conn, "AAPL")
    seed_security(conn, "MSFT")
    for d in ("2024-01-02", "2024-01-03", "2024-01-04"):
        insert_price(conn, "MSFT", d, 1, 1, 1, 1)
    # AAPL is missing 2024-01-03, which MSFT proves was a trading day
    insert_price(conn, "AAPL", "2024-01-02", 1, 1, 1, 1)
    insert_price(conn, "AAPL", "2024-01-04", 1, 1, 1, 1)

    _, rows = run_checks(conn)["missing_trading_days"]
    assert rows == [("AAPL", "2024-01-03")]


def test_stale_symbols_catches_lagging_symbol_and_is_fast(conn):
    # Regression test for the planner trap: this check used to cross-join
    # against an unmaterialized CTE and effectively re-scan the whole table
    # per row. 500 rows is enough to turn an O(n^2) regression into a
    # multi-second test instead of an instant one, without being slow itself.
    seed_security(conn, "AAPL")
    seed_security(conn, "MSFT")
    dates = [f"2024-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    for d in dates:
        insert_price(conn, "MSFT", d, 1, 1, 1, 1)
    for d in dates[:-1]:  # AAPL is missing the very last date
        insert_price(conn, "AAPL", d, 1, 1, 1, 1)

    t0 = time.time()
    _, rows = run_checks(conn)["stale_symbols"]
    elapsed = time.time() - t0

    assert rows == [("AAPL", dates[-2])]
    assert elapsed < 2.0


def test_unexplained_price_jump_is_flagged(conn):
    seed_security(conn, "AAPL")
    insert_price(conn, "AAPL", "2024-01-02", 10, 10, 10, 10)
    insert_price(conn, "AAPL", "2024-01-03", 30, 30, 30, 30)  # +200%, no action recorded

    _, rows = run_checks(conn)["unexplained_price_jumps"]
    assert len(rows) == 1


def test_price_jump_with_matching_action_is_not_flagged(conn):
    seed_security(conn, "AAPL")
    insert_price(conn, "AAPL", "2024-01-02", 10, 10, 10, 10)
    insert_price(conn, "AAPL", "2024-01-03", 30, 30, 30, 30)
    conn.execute(
        "INSERT INTO corporate_actions (symbol, date, action_type, value) "
        "VALUES ('AAPL', '2024-01-03', 'split', 3)"
    )

    _, rows = run_checks(conn)["unexplained_price_jumps"]
    assert rows == []


def test_invalid_corporate_action_is_flagged(conn):
    seed_security(conn, "AAPL")
    conn.execute(
        "INSERT INTO corporate_actions (symbol, date, action_type, value) "
        "VALUES ('AAPL', '2024-01-02', 'dividend', -1)"
    )

    _, rows = run_checks(conn)["invalid_corporate_actions"]
    assert len(rows) == 1


def test_backfill_not_completed_is_flagged(conn):
    seed_security(conn, "AAPL")
    conn.execute(
        "INSERT INTO backfill_status (symbol, status, last_backfill_date) "
        "VALUES ('AAPL', 'pending', '2024-01-01')"
    )

    _, rows = run_checks(conn)["backfill_not_completed"]
    assert len(rows) == 1
