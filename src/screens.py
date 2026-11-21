import re
import sqlite3
from pathlib import Path

SCREENS_PATH = Path(__file__).resolve().parent.parent / "sql" / "screens.sql"
DB_PATH = "data/market.db"

NAME_MARKER = re.compile(r"-- name:\s*(\w+)\s*\n")


def load_screens(path: Path = SCREENS_PATH) -> dict[str, str]:
    text = path.read_text()
    parts = NAME_MARKER.split(text)[1:]
    return dict(zip(parts[0::2], parts[1::2]))


def _fetch(cur: sqlite3.Cursor, top_n: int | None) -> list[tuple]:
    return cur.fetchall() if top_n is None else cur.fetchmany(top_n)


def momentum_screen(conn: sqlite3.Connection, lookback_days: int = 252, top_n: int | None = 10):
    """top_n=None returns the whole ranked universe."""
    sql = load_screens()["momentum"].format(lookback_days=lookback_days)
    return _fetch(conn.execute(sql), top_n)


def volatility_screen(conn: sqlite3.Connection, window_days: int = 63, top_n: int | None = 10):
    """top_n=None returns the whole ranked universe."""
    sql = load_screens()["volatility"].format(window_days=window_days)
    return _fetch(conn.execute(sql), top_n)


def print_rows(title: str, columns: list[str], rows: list[tuple]) -> None:
    print(title)
    for row in rows:
        print(f"    {dict(zip(columns, row))}")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)

    print_rows(
        "Top 10 by 12-month momentum:",
        ["symbol", "name", "close_start", "close_end", "momentum"],
        momentum_screen(conn, lookback_days=252, top_n=10),
    )
    print_rows(
        "Lowest 10 by 3-month annualized volatility:",
        ["symbol", "name", "annualized_volatility"],
        volatility_screen(conn, window_days=63, top_n=10),
    )
