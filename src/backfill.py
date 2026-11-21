from datetime import date, timedelta

from fetch import NoTradingDaysError, RateLimitError, SymbolNotFoundError, fetch_symbol
from load import get_connection, load_corporate_actions, load_daily_prices, load_securities
from universe import get_sp100_constituents

DB_PATH = "data/market.db"

END = date.today()
START = END.replace(year=END.year - 5)  # Fetch last 5 years of data on first load

end_str = END.isoformat()
start_str = START.isoformat()


def seed_backfill_status(conn, symbols):
    rows = [(symbol, "pending", end_str) for symbol in symbols]
    conn.executemany(
        """
        INSERT INTO backfill_status (symbol, status, last_backfill_date)
        VALUES (?, ?, ?)
        ON CONFLICT (symbol) DO NOTHING
        """,
        rows,
    )
    conn.commit()


def mark_status(conn, symbol, status, error=None):
    conn.execute(
        """
        UPDATE backfill_status
        SET status = ?, last_backfill_date = ?, last_error = ?
        WHERE symbol = ?
        """,
        (status, date.today().isoformat(), error, symbol),
    )
    conn.commit()


PERMANENT_FAILURE_TYPES = ("SymbolNotFoundError",)


def get_symbols_to_process(conn):
    # 'completed' is included too: it means the last run succeeded, not that
    # the symbol is done forever. Each run tops completed symbols up to the
    # latest trading day via get_fetch_start, so a short-lived gap (e.g. a
    # day dropped for missing data, like SNDK's unsettled close) gets
    # retried instead of frozen in place.
    rows = conn.execute(
        "SELECT symbol, status, last_error FROM backfill_status "
        "WHERE status IN ('pending', 'failed', 'in_progress', 'completed')"
    ).fetchall()
    return [
        symbol
        for symbol, status, last_error in rows
        if not (
            status == "failed"
            and (last_error or "").startswith(PERMANENT_FAILURE_TYPES)
        )
    ]


def get_fetch_start(conn, symbol):
    """Start date for this symbol: the day after its last loaded row, or the
    global 5-year START if it has no data yet."""
    row = conn.execute(
        "SELECT MAX(date) FROM daily_prices WHERE symbol = ?", (symbol,)
    ).fetchone()
    last_date = row[0]
    if last_date is None:
        return start_str
    return (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()


def run_backfill():
    conn = get_connection(DB_PATH)

    constituents = get_sp100_constituents()
    load_securities(conn, constituents)
    seed_backfill_status(conn, constituents["symbol"])

    symbols = get_symbols_to_process(conn)
    print(f"{len(symbols)} symbols to process")

    for symbol in symbols:
        fetch_start = get_fetch_start(conn, symbol)
        if fetch_start >= end_str:
            continue  # yfinance's end is exclusive, so nothing new to fetch

        mark_status(conn, symbol, "in_progress")
        try:
            bars, actions = fetch_symbol(symbol, fetch_start, end_str)
            load_daily_prices(conn, symbol, bars)
            load_corporate_actions(conn, symbol, actions)
            mark_status(conn, symbol, "completed")
        except NoTradingDaysError:
            mark_status(conn, symbol, "completed")
        except SymbolNotFoundError as e:
            mark_status(conn, symbol, "failed", f"{type(e).__name__}: {e}")
        except RateLimitError as e:
            mark_status(conn, symbol, "pending", f"{type(e).__name__}: {e}")
            print(f"Rate limited on {symbol}, stopping run: {e}")
            break

    counts = conn.execute(
        "SELECT status, COUNT(*) FROM backfill_status GROUP BY status"
    ).fetchall()
    print("Backfill summary:", dict(counts))


if __name__ == "__main__":
    run_backfill()
