import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"

ACTION_TYPE_MAP = {"Dividends": "dividend", "Stock Splits": "split"}


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def load_securities(conn: sqlite3.Connection, securities: pd.DataFrame) -> None:
    rows = securities[["symbol", "name", "sector", "added_date"]].itertuples(
        index=False, name=None
    )
    conn.executemany(
        """
        INSERT INTO securities (symbol, name, sector, added_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            name = excluded.name,
            sector = excluded.sector,
            added_date = excluded.added_date
        """,
        rows,
    )
    conn.commit()


def load_daily_prices(conn: sqlite3.Connection, symbol: str, bars: pd.DataFrame) -> None:
    bars = bars.reset_index()
    rows = [
        (
            symbol,
            row["Date"].strftime("%Y-%m-%d"),
            row["Open"],
            row["High"],
            row["Low"],
            row["Close"],
            row["Volume"],
        )
        for _, row in bars.iterrows()
    ]
    conn.executemany(
        """
        INSERT INTO daily_prices (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume
        """,
        rows,
    )
    conn.commit()


def load_corporate_actions(conn: sqlite3.Connection, symbol: str, actions: pd.DataFrame) -> None:
    actions = actions.reset_index()
    long = actions.melt(
        id_vars=["Date"],
        value_vars=list(ACTION_TYPE_MAP),
        var_name="raw_type",
        value_name="value",
    )
    long = long[long["value"] != 0]
    long["action_type"] = long["raw_type"].map(ACTION_TYPE_MAP)

    rows = [
        (symbol, row["Date"].strftime("%Y-%m-%d"), row["action_type"], row["value"])
        for _, row in long.iterrows()
    ]
    conn.executemany(
        """
        INSERT INTO corporate_actions (symbol, date, action_type, value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (symbol, date, action_type) DO UPDATE SET
            value = excluded.value
        """,
        rows,
    )
    conn.commit()
