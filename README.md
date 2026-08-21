# market-warehouse

ETL pipeline and equity screener. Ingests daily OHLCV for the S&P 100
into SQLite, runs data-quality checks, and builds momentum/volatility
screens with SQL window functions.

## Decisions

**Universe:** S&P 100, 5 years daily (~126k rows). Note this list is
survivorship-biased — delisted and acquired names are missing, so
aggregate stats skew upward. Fixing it needs point-in-time constituent
data, which isn't free.

**Source:** yfinance. It batches multiple tickers per request, so the
backfill runs in minutes; Alpha Vantage (25 req/day) and Tiingo
(50 req/hr) would take days and hours. Tradeoff is that yfinance is
unofficial and can break — so vendor code stays isolated in
`src/fetch.py` and nothing else imports it. Tiingo configured as
fallback and cross-validation source.

**Price adjustment:** store raw OHLCV plus a separate corporate actions
table; adjust in SQL at query time. Adjusted prices get rewritten
whenever an issuer pays a dividend or splits, so an adjusted table
can't be append-only. Raw prices never change, which keeps reloads
genuinely idempotent.

## Status

Phase 0 (setup) complete.