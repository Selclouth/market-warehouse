-- Data-quality checks for the warehouse. Each query should return zero rows
-- when the data is clean; any row returned is a finding to review.

-- name: ohlc_consistency
-- Prices that violate basic OHLC invariants (high is the max, low is the
-- min, nothing is zero or negative).
SELECT symbol, date, open, high, low, close, volume
FROM daily_prices
WHERE high < open OR high < close OR high < low
   OR low > open OR low > close
   OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0;

-- name: zero_volume
-- Zero-volume sessions. Real for a thinly traded name on a holiday half-day,
-- but every S&P 100 constituent is liquid enough that this almost always
-- means a bad or missing print rather than genuinely no trades.
SELECT symbol, date, volume
FROM daily_prices
WHERE volume = 0;

-- name: missing_trading_days
-- Trading days present in the warehouse's overall calendar (i.e. traded by
-- some other symbol) that are missing for a symbol, within that symbol's own
-- first-to-last date range. Scoped per symbol so newer listings (e.g. a
-- recent spinoff or re-IPO) aren't flagged for days before they existed.
WITH calendar AS (
    SELECT DISTINCT date FROM daily_prices
),
symbol_range AS (
    SELECT symbol, MIN(date) AS start_date, MAX(date) AS end_date
    FROM daily_prices
    GROUP BY symbol
)
SELECT sr.symbol, c.date AS missing_date
FROM symbol_range sr
JOIN calendar c ON c.date BETWEEN sr.start_date AND sr.end_date
LEFT JOIN daily_prices dp ON dp.symbol = sr.symbol AND dp.date = c.date
WHERE dp.symbol IS NULL;

-- name: stale_symbols
-- Symbols whose most recent loaded date lags behind the warehouse's overall
-- latest date. missing_trading_days only catches gaps inside a symbol's
-- existing range, so a symbol that's simply behind (e.g. a row dropped for
-- an unsettled close, then marked completed before the gap was filled)
-- wouldn't otherwise be flagged.
--
-- Written as a scalar subquery rather than a CTE cross-joined against
-- daily_prices: SQLite's planner didn't materialize that CTE here and
-- instead re-ran the MAX(date) scan once per row (O(n^2) -- 125k^2 -- hung
-- for minutes on this table). The scalar subquery form is correctly
-- evaluated once (confirmed via EXPLAIN QUERY PLAN: "SCALAR SUBQUERY").
SELECT symbol, MAX(date) AS symbol_latest
FROM daily_prices
GROUP BY symbol
HAVING MAX(date) < (SELECT MAX(date) FROM daily_prices);

-- name: unexplained_price_jumps
-- Single-day moves bigger than 50% with no matching corporate action
-- recorded for that symbol and date. yfinance's close is already
-- split-adjusted at the source (see README), so a real split shouldn't
-- produce a jump at all; a jump this size with no recorded action is more
-- likely a bad print or missing data than an uncaptured split.
WITH changes AS (
    SELECT
        symbol,
        date,
        close,
        LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
    FROM daily_prices
)
SELECT c.symbol, c.date, c.prev_close, c.close,
       (c.close - c.prev_close) / c.prev_close AS pct_change
FROM changes c
LEFT JOIN corporate_actions ca ON ca.symbol = c.symbol AND ca.date = c.date
WHERE c.prev_close IS NOT NULL
  AND ABS((c.close - c.prev_close) / c.prev_close) > 0.5
  AND ca.symbol IS NULL;

-- name: invalid_corporate_actions
-- Dividend or split rows with a non-positive value.
SELECT symbol, date, action_type, value
FROM corporate_actions
WHERE value <= 0;

-- name: backfill_not_completed
-- Symbols the backfill loop never finished (still pending/in_progress, or
-- a non-permanent failure that could be retried).
SELECT symbol, status, last_error
FROM backfill_status
WHERE status != 'completed';
