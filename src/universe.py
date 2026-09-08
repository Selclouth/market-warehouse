import io
import logging
from pathlib import Path

import pandas as pd
import requests

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/S%26P_100"
USER_AGENT = "market-warehouse/0.1 (educational project; contact: prestonajuarez@gmail.com)"
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "sp100.csv"

logger = logging.getLogger(__name__)


def scrape_sp100() -> pd.DataFrame:
    response = requests.get(WIKIPEDIA_URL, headers={"User-Agent": USER_AGENT}, timeout=10)
    response.raise_for_status()

    tables = pd.read_html(io.StringIO(response.text))
    for table in tables:
        if set(table.columns) == {"Symbol", "Name", "Sector"}:
            constituents = table
            break
    else:
        raise ValueError("Could not find S&P 100 constituents table on Wikipedia page")

    constituents = constituents.rename(
        columns={"Symbol": "symbol", "Name": "name", "Sector": "sector"}
    )
    constituents["added_date"] = None
    return constituents[["symbol", "name", "sector", "added_date"]]


def get_sp100_constituents(cache_path: Path = DEFAULT_CACHE_PATH) -> pd.DataFrame:
    try:
        constituents = scrape_sp100()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        constituents.to_csv(cache_path, index=False)
        return constituents
    except Exception as e:
        logger.warning(
            "S&P 100 scrape failed (%s), falling back to cached copy at %s", e, cache_path
        )
        if not cache_path.exists():
            raise
        return pd.read_csv(cache_path)
