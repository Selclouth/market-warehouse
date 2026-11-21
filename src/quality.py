import re
import sqlite3
from pathlib import Path

CHECKS_PATH = Path(__file__).resolve().parent.parent / "sql" / "quality_checks.sql"
DB_PATH = "data/market.db"

# Splits the file on "-- name: <id>" markers so each check can be run and
# reported on individually, rather than as one opaque script.
NAME_MARKER = re.compile(r"-- name:\s*(\w+)\s*\n")


def load_checks(path: Path = CHECKS_PATH) -> dict[str, str]:
    text = path.read_text()
    parts = NAME_MARKER.split(text)[1:]  # drop leading text before first marker
    return dict(zip(parts[0::2], parts[1::2]))


def run_checks(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    results = {}
    for name, sql in load_checks().items():
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
        results[name] = (columns, rows)
    return results


def print_report(results: dict[str, tuple]) -> None:
    for name, (columns, rows) in results.items():
        status = "OK" if not rows else f"{len(rows)} finding(s)"
        print(f"[{status}] {name}")
        for row in rows[:5]:
            print(f"    {dict(zip(columns, row))}")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5} more")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    print_report(run_checks(conn))
