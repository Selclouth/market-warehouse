import yfinance as yf
import pandas as pd
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFRateLimitError, YFPricesMissingError


yf.config.debug.hide_exceptions = False


class FetchError(Exception):
    pass


class SymbolNotFoundError(FetchError):
    pass


class RateLimitError(FetchError):
    pass


class NoTradingDaysError(FetchError):
    pass


def fetch_symbol(ticker: str, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch raw OHLCV bars and corporate actions for one ticker.

    Returns (bars, actions) as separate DataFrames. Raises SymbolNotFoundError,
    RateLimitError, or NoTradingDaysError instead of yfinance's default of an
    empty DataFrame for all three cases.
    """
    try:
        raw = yf.Ticker(ticker).history(
            start=start, end=end, auto_adjust=False, actions=True
        )
    except YFRateLimitError as e:
        raise RateLimitError(f"Rate limit exceeded: {e}") from e
    except YFPricesMissingError as e:
        raise NoTradingDaysError(
            f"No trading days found for {ticker} between {start} and {end}: {e}"
        ) from e
    except HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise SymbolNotFoundError(f"Symbol {ticker} not found: {e}") from e
        raise

    action_cols = [
        c for c in ("Dividends", "Stock Splits", "Capital Gains")
        if c in raw.columns
    ]
    has_action = raw[action_cols].ne(0).any(axis=1)

    bars = raw.drop(columns=action_cols)
    actions = raw.loc[has_action, action_cols]

    return bars, actions
