-- Momentum/volatility screens over daily_prices.close. No split adjustment
-- is applied here: Yahoo's OHLC is already split-adjusted at the source even
-- with auto_adjust=False (verified empirically -- NVDA's close is continuous
-- across its real 2024-06-10 10:1 split). corporate_actions.split is kept
-- only as a historical record of the event, not something to reapply.
-- Window frame sizes can't be bound SQL parameters, so {lookback_days} /
-- {window_days} are filled in by src/screens.py before execution -- always
-- with internally-controlled integers, never user input.

-- name: momentum
-- Trailing {lookback_days}-trading-day return as of each symbol's latest
-- date, ranked highest first.
WITH latest AS (
    SELECT symbol, MAX(date) AS date FROM daily_prices GROUP BY symbol
),
lagged AS (
    SELECT
        symbol,
        date,
        close,
        LAG(close, {lookback_days}) OVER (PARTITION BY symbol ORDER BY date) AS close_lagged
    FROM daily_prices
)
SELECT
    l.symbol,
    s.name,
    lg.close_lagged AS close_start,
    lg.close AS close_end,
    (lg.close / lg.close_lagged) - 1 AS momentum
FROM latest l
JOIN lagged lg ON lg.symbol = l.symbol AND lg.date = l.date
JOIN securities s ON s.symbol = l.symbol
WHERE lg.close_lagged IS NOT NULL
ORDER BY momentum DESC;

-- name: volatility
-- Annualized realized volatility of daily returns over the trailing
-- {window_days} trading days as of each symbol's latest date, ranked
-- lowest first.
WITH returns AS (
    SELECT
        symbol,
        date,
        close / LAG(close) OVER (PARTITION BY symbol ORDER BY date) - 1 AS daily_return
    FROM daily_prices
),
windowed AS (
    SELECT
        symbol,
        date,
        AVG(daily_return) OVER (
            PARTITION BY symbol ORDER BY date
            ROWS BETWEEN {window_days} - 1 PRECEDING AND CURRENT ROW
        ) AS mean_return,
        AVG(daily_return * daily_return) OVER (
            PARTITION BY symbol ORDER BY date
            ROWS BETWEEN {window_days} - 1 PRECEDING AND CURRENT ROW
        ) AS mean_sq_return,
        COUNT(daily_return) OVER (
            PARTITION BY symbol ORDER BY date
            ROWS BETWEEN {window_days} - 1 PRECEDING AND CURRENT ROW
        ) AS n
    FROM returns
    WHERE daily_return IS NOT NULL
),
latest AS (
    SELECT symbol, MAX(date) AS date FROM windowed GROUP BY symbol
)
SELECT
    w.symbol,
    s.name,
    SQRT(w.mean_sq_return - w.mean_return * w.mean_return) * SQRT(252) AS annualized_volatility
FROM latest l
JOIN windowed w ON w.symbol = l.symbol AND w.date = l.date
JOIN securities s ON s.symbol = l.symbol
WHERE w.n >= {window_days}
ORDER BY annualized_volatility ASC;
