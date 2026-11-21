import pytest

from analytics import coverage, price_history, quality_summary, risk_return
from screens import momentum_screen


def seed(conn, symbol, closes, sector="Tech"):
    conn.execute("INSERT INTO securities (symbol, name, sector) VALUES (?, ?, ?)", (symbol, symbol, sector))
    for i, c in enumerate(closes):
        conn.execute(
            "INSERT INTO daily_prices (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, 1000)",
            (symbol, f"2024-01-{i + 1:02d}", c, c, c, c),
        )


def test_screens_return_whole_universe_when_top_n_is_none(conn):
    for i in range(12):
        seed(conn, f"S{i:02d}", [100, 100 + i])
    assert len(momentum_screen(conn, lookback_days=1, top_n=None)) == 12
    assert len(momentum_screen(conn, lookback_days=1)) == 10


def test_risk_return_joins_both_screens_and_sector(conn):
    seed(conn, "AAPL", [100, 110, 99, 120], sector="Tech")
    seed(conn, "XOM", [100, 101, 100, 102], sector="Energy")

    df = risk_return(conn, lookback_days=3, window_days=3)

    assert list(df["symbol"]) == ["AAPL", "XOM"]  # ranked by momentum
    aapl = df.iloc[0]
    assert aapl["sector"] == "Tech"
    assert aapl["momentum"] == pytest.approx(0.20)
    assert aapl["return_per_vol"] == pytest.approx(aapl["momentum"] / aapl["volatility"])


def test_risk_return_drops_symbols_missing_either_screen(conn):
    seed(conn, "LONG", [100, 110, 99, 120])
    seed(conn, "SHORT", [100, 110])  # not enough history for either window

    df = risk_return(conn, lookback_days=3, window_days=3)

    assert list(df["symbol"]) == ["LONG"]


def test_price_history_indexes_to_100_over_lookback_window(conn):
    seed(conn, "AAPL", [50, 100, 120, 80])

    df = price_history(conn, ["AAPL"], lookback_days=2)

    assert list(df["close"]) == [100, 120, 80]  # last lookback+1 sessions
    assert list(df["indexed"]) == pytest.approx([100, 120, 80])


def test_price_history_empty_selection(conn):
    assert price_history(conn, [], lookback_days=5).empty


def test_coverage_and_quality_summary(conn):
    seed(conn, "AAPL", [100, 101])
    conn.execute("INSERT INTO securities (symbol, name) VALUES ('EMPTY', 'Empty')")

    cov = coverage(conn).set_index("symbol")
    assert cov.loc["AAPL", "rows"] == 2
    assert cov.loc["EMPTY", "rows"] == 0

    summary, findings = quality_summary(conn)
    assert set(summary["check"]) == set(findings)
    assert (summary["findings"] == summary["check"].map(lambda c: len(findings[c]))).all()
