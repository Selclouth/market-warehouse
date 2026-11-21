# market-warehouse

ETL pipeline and equity screener. Ingests daily OHLCV for the S&P 100
into SQLite, runs data-quality checks, and builds momentum/volatility
screens with SQL window functions.

## Decisions

**Universe:** S&P 100, 5 years daily (~126k rows). Note this list is
survivorship-biased (delisted and acquired names are missing), so
aggregate stats skew upward. Fixing it needs point-in-time constituent
data, which isn't free.

**Source:** yfinance. It batches multiple tickers per request, so the
backfill runs in minutes; Alpha Vantage (25 req/day) and Tiingo
(50 req/hr) would take days and hours. Tradeoff is that yfinance is
unofficial and can break, so vendor code stays isolated in
`src/fetch.py` and nothing else imports it. Tiingo configured as
fallback and cross-validation source.

**Price adjustment:** originally planned to store raw OHLCV plus a
separate corporate actions table and adjust for splits in SQL at query
time. Turned out unnecessary: yfinance's OHLC is already split-adjusted
at the source even with `auto_adjust=False` (verified empirically —
NVDA's close is continuous across its real 2024-06-10 10:1 split, no
10x jump). `corporate_actions.split` is kept only as a historical
record of when a split happened; reapplying it to price data double-
adjusts and produces wrong numbers (caught this via a bogus 1830%
"momentum" reading for BKNG before fixing it). One real consequence:
since splits are baked in at the source, a symbol's historical close
values can change if Yahoo's backend reprocesses them after a future
split, so raw prices aren't actually immutable the way "append-only"
implies — the loader's upsert-on-conflict handles that fine as long as
the symbol gets re-fetched. Dividends are not baked into `close`
(confirmed by comparing to yfinance's separate `Adj Close` column), so
raw OHLCV is stable with respect to dividends; a future total-return
screen would still need real dividend-adjustment math.

**Error handling:** `src/fetch.py` distinguishes three failure modes
(bad symbol, rate limit, no trading days in range) as separate
exception types, so callers can retry, skip, or no-op appropriately.
This required going around yfinance's default behavior, which swallows
all three into a warning plus an empty DataFrame
(`yf.config.debug.hide_exceptions = False` turns that off). It also
required catching `curl_cffi`'s `HTTPError`, not `requests`': yfinance
1.6.0 uses `curl_cffi` for its HTTP layer internally, so a bad-symbol
404 surfaces as `curl_cffi.requests.exceptions.HTTPError`, a different
class from the one in the standard `requests` library despite the
matching name and interface.

## Status

Phase 0 (setup), Phase 1 (single-symbol fetch), Phase 2 (schema,
loaders, and resumable backfill), Phase 3 (data-quality checks), and
Phase 4 (momentum/volatility screens) complete. `data/market.db` holds
full 5-year history for all 101 S&P 100 constituents (~125k price
rows), `src/quality.py` runs clean against it, and `src/screens.py`
ranks the universe by trailing momentum and realized volatility.
