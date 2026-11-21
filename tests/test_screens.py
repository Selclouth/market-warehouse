import statistics

import pytest

from screens import momentum_screen, volatility_screen


def seed_security(conn, symbol):
    conn.execute("INSERT INTO securities (symbol, name) VALUES (?, ?)", (symbol, symbol))


def insert_price(conn, symbol, date, close):
    conn.execute(
        "INSERT INTO daily_prices (symbol, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, 1000)",
        (symbol, date, close, close, close, close),
    )


def test_momentum_is_pct_return_over_lookback_window(conn):
    seed_security(conn, "AAPL")
    closes = [100, 110, 120]
    for i, close in enumerate(closes):
        insert_price(conn, "AAPL", f"2024-01-{i + 1:02d}", close)

    rows = momentum_screen(conn, lookback_days=2, top_n=10)

    assert len(rows) == 1
    symbol, name, close_start, close_end, momentum = rows[0]
    assert symbol == "AAPL"
    assert close_start == 100
    assert close_end == 120
    assert momentum == pytest.approx(120 / 100 - 1)


def test_momentum_excludes_symbols_without_enough_history(conn):
    seed_security(conn, "AAPL")
    insert_price(conn, "AAPL", "2024-01-01", 100)  # only one row

    rows = momentum_screen(conn, lookback_days=2, top_n=10)

    assert rows == []


def test_momentum_ranks_highest_return_first(conn):
    seed_security(conn, "AAPL")
    seed_security(conn, "MSFT")
    for i, close in enumerate([100, 100, 150]):  # +50%
        insert_price(conn, "AAPL", f"2024-01-{i + 1:02d}", close)
    for i, close in enumerate([100, 100, 110]):  # +10%
        insert_price(conn, "MSFT", f"2024-01-{i + 1:02d}", close)

    rows = momentum_screen(conn, lookback_days=2, top_n=10)

    assert [r[0] for r in rows] == ["AAPL", "MSFT"]


def test_volatility_matches_independently_computed_stdev(conn):
    seed_security(conn, "AAPL")
    closes = [100, 110, 99, 108]
    for i, close in enumerate(closes):
        insert_price(conn, "AAPL", f"2024-01-{i + 1:02d}", close)

    daily_returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    expected_vol = statistics.pstdev(daily_returns) * (252 ** 0.5)

    rows = volatility_screen(conn, window_days=3, top_n=10)

    assert len(rows) == 1
    symbol, name, annualized_volatility = rows[0]
    assert symbol == "AAPL"
    assert annualized_volatility == pytest.approx(expected_vol, rel=1e-6)


def test_volatility_excludes_symbols_without_a_full_window(conn):
    seed_security(conn, "AAPL")
    for i, close in enumerate([100, 110, 99]):  # only 2 returns, window needs 3
        insert_price(conn, "AAPL", f"2024-01-{i + 1:02d}", close)

    rows = volatility_screen(conn, window_days=3, top_n=10)

    assert rows == []


def test_volatility_ranks_lowest_first(conn):
    seed_security(conn, "CALM")
    seed_security(conn, "WILD")
    for i, close in enumerate([100, 101, 100, 101]):
        insert_price(conn, "CALM", f"2024-01-{i + 1:02d}", close)
    for i, close in enumerate([100, 150, 60, 140]):
        insert_price(conn, "WILD", f"2024-01-{i + 1:02d}", close)

    rows = volatility_screen(conn, window_days=3, top_n=10)

    assert [r[0] for r in rows] == ["CALM", "WILD"]
