from backfill import end_str, get_fetch_start, get_symbols_to_process, start_str


def seed_security(conn, symbol):
    conn.execute("INSERT INTO securities (symbol, name) VALUES (?, ?)", (symbol, symbol))


def test_get_fetch_start_returns_global_start_for_new_symbol(conn):
    seed_security(conn, "AAPL")
    assert get_fetch_start(conn, "AAPL") == start_str


def test_get_fetch_start_returns_day_after_last_loaded_row(conn):
    seed_security(conn, "AAPL")
    conn.execute(
        "INSERT INTO daily_prices (symbol, date, open, high, low, close, volume) "
        "VALUES ('AAPL', '2024-06-10', 1, 1, 1, 1, 1)"
    )
    assert get_fetch_start(conn, "AAPL") == "2024-06-11"


def test_get_symbols_to_process_includes_completed_for_top_up(conn):
    # 'completed' must be retried each run (not skipped forever), so a short
    # gap -- like SNDK's dropped row for an unsettled close -- can heal.
    seed_security(conn, "AAPL")
    conn.execute(
        "INSERT INTO backfill_status (symbol, status, last_backfill_date) "
        "VALUES ('AAPL', 'completed', ?)",
        (end_str,),
    )
    assert get_symbols_to_process(conn) == ["AAPL"]


def test_get_symbols_to_process_excludes_permanent_failure(conn):
    seed_security(conn, "FAKE")
    conn.execute(
        "INSERT INTO backfill_status (symbol, status, last_backfill_date, last_error) "
        "VALUES ('FAKE', 'failed', ?, 'SymbolNotFoundError: not found')",
        (end_str,),
    )
    assert get_symbols_to_process(conn) == []


def test_get_symbols_to_process_includes_retryable_failure(conn):
    seed_security(conn, "AAPL")
    conn.execute(
        "INSERT INTO backfill_status (symbol, status, last_backfill_date, last_error) "
        "VALUES ('AAPL', 'failed', ?, 'RateLimitError: rate limited')",
        (end_str,),
    )
    assert get_symbols_to_process(conn) == ["AAPL"]
