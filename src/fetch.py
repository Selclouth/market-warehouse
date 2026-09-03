import yfinance as yf
import pandas as pd
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFRateLimitError, YFPricesMissingError

yf.config.debug.hide_exceptions = False



class FetchError(Exception):
    """Custom exception for fetch errors."""
    pass

class SymbolNotFoundError(FetchError):
    """Custom exception for symbol not found errors."""
    pass


class RateLimitError(FetchError):
    """Custom exception for rate limit errors."""
    pass

class NoTradingDaysError(FetchError):
    """Custom exception for no trading days errors."""
    pass

def fetch_symbol(ticker: str, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        raw = yf.Ticker(ticker).history(
            start=start, end=end, auto_adjust=False, actions=True
        )
    except YFRateLimitError as e:
        raise RateLimitError(f"Rate limit exceeded: {e}")
    except YFPricesMissingError as e:
        raise NoTradingDaysError(
            f"No trading days found for {ticker} between {start} and {end}: {e}"
        )
    except HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise SymbolNotFoundError(f"Symbol {ticker} not found: {e}")
        raise

    action_cols = [
        c for c in ("Dividends", "Stock Splits", "Capital Gains")
        if c in raw.columns
    ]
    has_action = raw[action_cols].ne(0).any(axis=1)

    bars = raw.drop(columns=action_cols)
    actions = raw.loc[has_action, action_cols]

    return bars, actions
