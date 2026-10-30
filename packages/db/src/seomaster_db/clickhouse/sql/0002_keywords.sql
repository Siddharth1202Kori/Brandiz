-- Normalized keyword metrics (one row per fetch; ReplacingMergeTree keeps the newest per
-- market+keyword). Read with FINAL or argMax. Feeds list items and the nightly refresh.
CREATE TABLE IF NOT EXISTS keyword_metrics
(
    market        LowCardinality(String),
    keyword       String,
    volume        Nullable(UInt32),
    cpc           Nullable(Float32),
    competition   Nullable(Float32),
    kd            Nullable(UInt8),
    intents       Array(LowCardinality(String)),
    trend         Array(Nullable(UInt32)),
    trend_months  Array(String),
    serp_features Array(LowCardinality(String)),
    source        LowCardinality(String),
    fetched_at    DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY (market, keyword);

-- Top-10 organic SERP history (one row per fetch), kept 13 months for "SERP changed" views.
CREATE TABLE IF NOT EXISTS serp_snapshots
(
    taken_at  DateTime64(3, 'UTC'),
    market    LowCardinality(String),
    keyword   String,
    device    LowCardinality(String),
    positions Array(UInt16),
    urls      Array(String),
    domains   Array(String),
    titles    Array(Nullable(String)),
    features  Array(LowCardinality(String))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(taken_at)
ORDER BY (market, keyword, taken_at)
TTL toDateTime(taken_at) + INTERVAL 13 MONTH;
