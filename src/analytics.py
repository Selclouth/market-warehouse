"""DataFrame builders for the dashboard. Read-only against the warehouse;
every function takes an open connection so tests can use the in-memory db."""

import sqlite3

import pandas as pd

from quality import run_checks
from screens import momentum_screen, volatility_screen


def risk_return(conn: sqlite3.Connection, lookback_days: int = 252, window_days: int = 63) -> pd.DataFrame:
    """One row per symbol with both momentum and volatility. Symbols missing
    either (not enough history) are dropped."""
    mom = pd.DataFrame(
        momentum_screen(conn, lookback_days=lookback_days, top_n=None),
        columns=["symbol", "name", "close_start", "close_end", "momentum"],
    )
    vol = pd.DataFrame(
        volatility_screen(conn, window_days=window_days, top_n=None),
        columns=["symbol", "name", "volatility"],
    ).drop(columns="name")
    sectors = pd.read_sql("SELECT symbol, COALESCE(sector, 'Unknown') AS sector FROM securities", conn)
    df = mom.merge(vol, on="symbol").merge(sectors, on="symbol")
    df["return_per_vol"] = df["momentum"] / df["volatility"]
    return df.sort_values("momentum", ascending=False).reset_index(drop=True)


def price_history(conn: sqlite3.Connection, symbols: list[str], lookback_days: int = 252) -> pd.DataFrame:
    """Closes for `symbols` over each one's last `lookback_days` + 1 sessions
    (the momentum window, inclusive of its start), indexed to 100 at the start."""
    if not symbols:
        return pd.DataFrame(columns=["symbol", "date", "close", "indexed"])
    placeholders = ",".join("?" * len(symbols))
    df = pd.read_sql(
        f"""
        SELECT symbol, date, close FROM (
            SELECT symbol, date, close,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM daily_prices WHERE symbol IN ({placeholders})
        ) WHERE rn <= ?
        ORDER BY symbol, date
        """,
        conn,
        params=[*symbols, lookback_days + 1],
    )
    df["date"] = pd.to_datetime(df["date"])
    df["indexed"] = df["close"] / df.groupby("symbol")["close"].transform("first") * 100
    return df


def coverage(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-symbol row count and date range, plus backfill status."""
    return pd.read_sql(
        """
        SELECT s.symbol, s.sector, COUNT(p.date) AS rows,
               MIN(p.date) AS first_date, MAX(p.date) AS last_date,
               b.status AS backfill_status
        FROM securities s
        LEFT JOIN daily_prices p ON p.symbol = s.symbol
        LEFT JOIN backfill_status b ON b.symbol = s.symbol
        GROUP BY s.symbol
        ORDER BY rows ASC, s.symbol
        """,
        conn,
    )


def quality_summary(conn: sqlite3.Connection) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """(one row per check with its finding count, {check: findings frame})."""
    results = run_checks(conn)
    findings = {name: pd.DataFrame(rows, columns=cols) for name, (cols, rows) in results.items()}
    summary = pd.DataFrame(
        [{"check": name, "findings": len(df)} for name, df in findings.items()]
    )
    return summary, findings
