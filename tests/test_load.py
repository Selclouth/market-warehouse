import pandas as pd

from load import load_corporate_actions, load_daily_prices, load_securities


def make_bars(rows):
    """rows: list of (date_str, open, high, low, close, volume)."""
    index = pd.to_datetime([r[0] for r in rows])
    index.name = "Date"
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=index,
    )


def test_load_securities_inserts_then_upserts(conn):
    first = pd.DataFrame(
        [{"symbol": "AAPL", "name": "Apple", "sector": "Tech", "added_date": None}]
    )
    load_securities(conn, first)

    second = pd.DataFrame(
        [{"symbol": "AAPL", "name": "Apple Inc.", "sector": "Tech", "added_date": None}]
    )
    load_securities(conn, second)

    rows = conn.execute("SELECT symbol, name FROM securities").fetchall()
    assert rows == [("AAPL", "Apple Inc.")]


def test_load_daily_prices_is_idempotent_and_upserts(conn):
    conn.execute(
        "INSERT INTO securities (symbol, name) VALUES ('AAPL', 'Apple')"
    )

    bars = make_bars([("2024-01-02", 10, 11, 9, 10.5, 100)])
    load_daily_prices(conn, "AAPL", bars)
    load_daily_prices(conn, "AAPL", bars)  # reload same data: must not duplicate

    rows = conn.execute("SELECT date, close FROM daily_prices WHERE symbol='AAPL'").fetchall()
    assert rows == [("2024-01-02", 10.5)]

    updated_bars = make_bars([("2024-01-02", 10, 11, 9, 20.0, 100)])
    load_daily_prices(conn, "AAPL", updated_bars)

    rows = conn.execute("SELECT date, close FROM daily_prices WHERE symbol='AAPL'").fetchall()
    assert rows == [("2024-01-02", 20.0)]


def test_load_corporate_actions_skips_zero_values_and_maps_types(conn):
    conn.execute(
        "INSERT INTO securities (symbol, name) VALUES ('AAPL', 'Apple')"
    )

    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    index.name = "Date"
    actions = pd.DataFrame(
        {"Dividends": [0.0, 0.24], "Stock Splits": [0.0, 0.0]},
        index=index,
    )
    load_corporate_actions(conn, "AAPL", actions)

    rows = conn.execute(
        "SELECT date, action_type, value FROM corporate_actions WHERE symbol='AAPL'"
    ).fetchall()
    assert rows == [("2024-01-03", "dividend", 0.24)]
