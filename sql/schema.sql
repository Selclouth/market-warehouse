CREATE TABLE IF NOT EXISTS securities (
    symbol      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT,
    added_date  TEXT
);

CREATE TABLE IF NOT EXISTS daily_prices (
    symbol      TEXT NOT NULL REFERENCES securities(symbol),
    date        TEXT NOT NULL,
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      INTEGER NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol      TEXT NOT NULL REFERENCES securities(symbol),
    date        TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('dividend', 'split')),
    value       REAL NOT NULL,
    PRIMARY KEY (symbol, date, action_type)
);
