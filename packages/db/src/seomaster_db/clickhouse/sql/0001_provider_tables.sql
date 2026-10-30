-- Durable provider cache (warm tier behind Redis). ReplacingMergeTree keeps the newest
-- fetch per key. Rows stay 30 days past expiry so the budget guard can serve stale data.
CREATE TABLE IF NOT EXISTS provider_payloads
(
    key        String,
    provider   LowCardinality(String),
    endpoint   LowCardinality(String),
    payload    String CODEC(ZSTD(3)),
    fetched_at DateTime64(3, 'UTC'),
    expires_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY key
TTL toDateTime(expires_at) + INTERVAL 30 DAY;

-- Cost ledger: one row per DAL lookup (hits too, so hit rate is measurable).
CREATE TABLE IF NOT EXISTS provider_calls
(
    created_at DateTime64(3, 'UTC'),
    provider   LowCardinality(String),
    endpoint   LowCardinality(String),
    cache_key  String,
    org_id     Nullable(UUID),
    cache_tier LowCardinality(String),
    cost_usd   Decimal(12, 6),
    latency_ms UInt32
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (provider, created_at);
