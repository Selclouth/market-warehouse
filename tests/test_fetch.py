from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from fetch import NoTradingDaysError, RateLimitError, SymbolNotFoundError, fetch_symbol


def make_bars(rows):
    """rows: list of (date_str, open, high, low, close, volume, splits, dividends)."""
    index = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
            "Stock Splits": [r[6] for r in rows],
            "Dividends": [r[7] for r in rows],
        },
        index=index,
    )


@patch("fetch.yf.Ticker")
def test_dotted_ticker_is_normalized_for_the_query(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_bars(
        [("2024-01-02", 1, 1, 1, 1, 100, 0, 0)]
    )
    mock_ticker_cls.return_value = mock_ticker

    fetch_symbol("BRK.B", "2024-01-01", "2024-01-03")

    queried_ticker = mock_ticker_cls.call_args[0][0]
    assert queried_ticker == "BRK-B"


@patch("fetch.yf.Ticker")
def test_plain_ticker_is_not_modified(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_bars(
        [("2024-01-02", 1, 1, 1, 1, 100, 0, 0)]
    )
    mock_ticker_cls.return_value = mock_ticker

    fetch_symbol("AAPL", "2024-01-01", "2024-01-03")

    assert mock_ticker_cls.call_args[0][0] == "AAPL"


@patch("fetch.yf.Ticker")
def test_rate_limit_is_raised_as_rate_limit_error(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = YFRateLimitError()
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(RateLimitError):
        fetch_symbol("AAPL", "2024-01-01", "2024-01-03")


@patch("fetch.yf.Ticker")
def test_no_prices_is_raised_as_no_trading_days_error(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = YFPricesMissingError("AAPL", "no prices")
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(NoTradingDaysError):
        fetch_symbol("AAPL", "2024-01-01", "2024-01-03")


@patch("fetch.yf.Ticker")
def test_tz_missing_is_raised_as_symbol_not_found_error(mock_ticker_cls):
    # Observed for BRK.B before the dot->hyphen normalization was added:
    # yfinance can't resolve a dotted ticker and raises this instead of a 404.
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = YFTzMissingError("BRK.B")
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(SymbolNotFoundError):
        fetch_symbol("BRK.B", "2024-01-01", "2024-01-03")


@patch("fetch.yf.Ticker")
def test_http_404_is_raised_as_symbol_not_found_error(mock_ticker_cls):
    response = MagicMock(status_code=404)
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = HTTPError("not found", response=response)
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(SymbolNotFoundError):
        fetch_symbol("NOTREAL", "2024-01-01", "2024-01-03")


@patch("fetch.yf.Ticker")
def test_non_404_http_error_propagates_unchanged(mock_ticker_cls):
    response = MagicMock(status_code=500)
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = HTTPError("server error", response=response)
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(HTTPError):
        fetch_symbol("AAPL", "2024-01-01", "2024-01-03")


@patch("fetch.yf.Ticker")
def test_rows_with_unsettled_nan_close_are_dropped(mock_ticker_cls):
    # Observed for SNDK: the most recent session's Close/Adj Close can be NaN
    # when Yahoo hasn't settled it yet. These rows must not reach the loader,
    # which has a NOT NULL constraint on close.
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_bars(
        [
            ("2024-01-02", 10, 11, 9, 10.5, 100, 0, 0),
            ("2024-01-03", 11, 12, 10, float("nan"), 150, 0, 0),
        ]
    )
    mock_ticker_cls.return_value = mock_ticker

    bars, _ = fetch_symbol("AAPL", "2024-01-01", "2024-01-04")

    assert len(bars) == 1
    assert bars.iloc[0]["Close"] == 10.5


@patch("fetch.yf.Ticker")
def test_actions_are_separated_from_bars(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_bars(
        [
            ("2024-01-02", 10, 11, 9, 10.5, 100, 0, 0),
            ("2024-01-03", 1, 1.1, 0.9, 1.05, 150, 10, 0),  # split day
        ]
    )
    mock_ticker_cls.return_value = mock_ticker

    bars, actions = fetch_symbol("AAPL", "2024-01-01", "2024-01-04")

    assert "Stock Splits" not in bars.columns
    assert "Dividends" not in bars.columns
    assert len(actions) == 1
    assert actions.iloc[0]["Stock Splits"] == 10
