from datetime import date

from fetch import NoTradingDaysError, RateLimitError, SymbolNotFoundError, fetch_symbol
from load import get_connection, load_corporate_actions, load_daily_prices, load_securities
from universe import get_sp100_constituents

DB_PATH = "data/market.db"

END = date.today()
START = END.replace(year=END.year - 5)  # Fetch last 5 years of data

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


def get_pending_symbols(conn):
    rows = conn.execute(
        "SELECT symbol, status, last_error FROM backfill_status "
        "WHERE status IN ('pending', 'failed', 'in_progress')"
    ).fetchall()
    return [
        symbol
        for symbol, status, last_error in rows
        if not (
            status == "failed"
            and (last_error or "").startswith(PERMANENT_FAILURE_TYPES)
        )
    ]


def run_backfill():
    conn = get_connection(DB_PATH)

    constituents = get_sp100_constituents()
    load_securities(conn, constituents)
    seed_backfill_status(conn, constituents["symbol"])

    symbols = get_pending_symbols(conn)
    print(f"{len(symbols)} symbols to process")

    for symbol in symbols:
        mark_status(conn, symbol, "in_progress")
        try:
            bars, actions = fetch_symbol(symbol, start_str, end_str)
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
