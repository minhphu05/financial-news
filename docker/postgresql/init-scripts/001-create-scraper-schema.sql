-- =============================================================================
-- Financial News Scraper - core + scraping schemas
-- =============================================================================
-- Target database : ${METADATA_POSTGRES_DB}  (default: financial_metadata)
-- Schemas         : core, scraping, rag
--
-- This script is idempotent for fresh container initialization and manual
-- re-application. It only creates/updates scraper-oriented schemas and does not
-- touch the existing rag_metadata schema or other application schemas.
-- =============================================================================

SET client_encoding = 'UTF8';
SET timezone = 'UTC';

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS scraping;
CREATE SCHEMA IF NOT EXISTS rag;

DO $$
BEGIN
    EXECUTE format('GRANT ALL PRIVILEGES ON SCHEMA core TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON SCHEMA scraping TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON SCHEMA rag TO %I', current_user);
END
$$;

-- =============================================================================
-- SCHEMA: CORE (refined business data for RAG/chatbot use)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core.stocks (
    stock_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker       VARCHAR(16)  NOT NULL UNIQUE,
    company_name VARCHAR(512) NOT NULL,
    exchange     VARCHAR(16),
    sector       VARCHAR(128),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.stocks IS 'Refined stock universe used by scraper, RAG, and downstream analytics.';
COMMENT ON COLUMN core.stocks.ticker IS 'Stock ticker, e.g. ACB, FPT, VCB.';
COMMENT ON COLUMN core.stocks.exchange IS 'HOSE, HNX, UPCOM.';
COMMENT ON COLUMN core.stocks.sector IS 'Business sector.';

CREATE TABLE IF NOT EXISTS core.index_memberships (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_id   UUID        NOT NULL REFERENCES core.stocks (stock_id) ON DELETE CASCADE,
    index_name VARCHAR(32) NOT NULL,
    joined_at  DATE        NOT NULL,
    left_at    DATE,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON COLUMN core.index_memberships.index_name IS 'Index basket name, e.g. VN30, HNX30.';
COMMENT ON COLUMN core.index_memberships.joined_at IS 'Date the stock joined the index basket.';
COMMENT ON COLUMN core.index_memberships.left_at IS 'Null means the stock is currently still in the basket.';

CREATE INDEX IF NOT EXISTS ix_core_index_memberships_stock_id ON core.index_memberships (stock_id);
CREATE INDEX IF NOT EXISTS ix_core_index_memberships_active ON core.index_memberships (index_name, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS uq_core_index_memberships_active
    ON core.index_memberships (stock_id, index_name)
    WHERE left_at IS NULL;

CREATE TABLE IF NOT EXISTS core.stock_metrics (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_id           UUID        NOT NULL REFERENCES core.stocks (stock_id) ON DELETE CASCADE,

    trading_date       DATE        NOT NULL,
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    is_eod             BOOLEAN     NOT NULL DEFAULT FALSE,
    session_note       VARCHAR(32),

    reference_price    NUMERIC(18, 4),
    ceiling_price      NUMERIC(18, 4),
    floor_price        NUMERIC(18, 4),

    bid_price_3        NUMERIC(18, 4),
    bid_volume_3       BIGINT,
    bid_price_2        NUMERIC(18, 4),
    bid_volume_2       BIGINT,
    bid_price_1        NUMERIC(18, 4),
    bid_volume_1       BIGINT,

    matched_price      NUMERIC(18, 4),
    matched_volume     BIGINT,
    change             NUMERIC(18, 4),
    change_percent     NUMERIC(12, 6),

    ask_price_1        NUMERIC(18, 4),
    ask_volume_1       BIGINT,
    ask_price_2        NUMERIC(18, 4),
    ask_volume_2       BIGINT,
    ask_price_3        NUMERIC(18, 4),
    ask_volume_3       BIGINT,

    total_volume       BIGINT,
    total_value        NUMERIC(24, 4),
    high_price         NUMERIC(18, 4),
    low_price          NUMERIC(18, 4),
    average_price      NUMERIC(18, 4),

    foreign_buy_volume  BIGINT,
    foreign_sell_volume BIGINT,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.stock_metrics IS 'Stock price-board snapshots scraped from market data sources such as Vietstock.';
COMMENT ON COLUMN core.stock_metrics.trading_date IS 'Trading date.';
COMMENT ON COLUMN core.stock_metrics.snapshot_timestamp IS 'Scrape timestamp, e.g. 12:00:00 or 17:00:00.';
COMMENT ON COLUMN core.stock_metrics.is_eod IS 'True when this snapshot is the final end-of-day value.';
COMMENT ON COLUMN core.stock_metrics.session_note IS 'MORNING, AFTERNOON, EOD.';
COMMENT ON COLUMN core.stock_metrics.reference_price IS 'Reference price.';
COMMENT ON COLUMN core.stock_metrics.ceiling_price IS 'Ceiling price.';
COMMENT ON COLUMN core.stock_metrics.floor_price IS 'Floor price.';
COMMENT ON COLUMN core.stock_metrics.matched_price IS 'Latest matched price.';
COMMENT ON COLUMN core.stock_metrics.matched_volume IS 'Latest matched volume.';
COMMENT ON COLUMN core.stock_metrics.change IS 'Price change.';
COMMENT ON COLUMN core.stock_metrics.change_percent IS 'Price change percentage.';
COMMENT ON COLUMN core.stock_metrics.total_volume IS 'Total trading volume.';
COMMENT ON COLUMN core.stock_metrics.total_value IS 'Total trading value.';
COMMENT ON COLUMN core.stock_metrics.high_price IS 'Session high price.';
COMMENT ON COLUMN core.stock_metrics.low_price IS 'Session low price.';
COMMENT ON COLUMN core.stock_metrics.average_price IS 'Average price.';
COMMENT ON COLUMN core.stock_metrics.foreign_buy_volume IS 'Foreign investor buy volume.';
COMMENT ON COLUMN core.stock_metrics.foreign_sell_volume IS 'Foreign investor sell volume.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_core_stock_snapshot ON core.stock_metrics (stock_id, snapshot_timestamp);
CREATE INDEX IF NOT EXISTS idx_core_stock_date ON core.stock_metrics (stock_id, trading_date);

-- =============================================================================
-- SCHEMA: SCRAPING (operational data and logs for scraping pipelines)
-- =============================================================================

CREATE TABLE IF NOT EXISTS scraping.sources (
    id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name      VARCHAR(64)  NOT NULL UNIQUE,
    base_url  VARCHAR(512),
    language  VARCHAR(16)  DEFAULT 'vi',
    is_active BOOLEAN      NOT NULL DEFAULT TRUE
);

COMMENT ON COLUMN scraping.sources.name IS 'Source name, e.g. baomoi, thanhnien, cafef, vnexpress, tuoitre, vietstock.';

CREATE TABLE IF NOT EXISTS scraping.proxies (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address   VARCHAR(64) NOT NULL,
    port         INTEGER     NOT NULL,
    protocol     VARCHAR(16),
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    fail_count   INTEGER     NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN scraping.proxies.protocol IS 'HTTP, HTTPS, SOCKS5.';

CREATE TABLE IF NOT EXISTS scraping.crawl_jobs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name         VARCHAR(256),
    job_type         VARCHAR(32),
    source_id        UUID        REFERENCES scraping.sources (id),

    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    status           VARCHAR(16),

    total_requests   INTEGER     NOT NULL DEFAULT 0,
    success_requests INTEGER     NOT NULL DEFAULT 0,
    failed_requests  INTEGER     NOT NULL DEFAULT 0,
    items_extracted  INTEGER     NOT NULL DEFAULT 0,

    crawler_version  VARCHAR(32),
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN scraping.crawl_jobs.job_name IS 'Example: CafeF scrape at 12:00.';
COMMENT ON COLUMN scraping.crawl_jobs.job_type IS 'NEWS, STOCK_METRICS.';
COMMENT ON COLUMN scraping.crawl_jobs.source_id IS 'Null for source-agnostic metric scraping jobs.';
COMMENT ON COLUMN scraping.crawl_jobs.status IS 'PENDING, RUNNING, SUCCESS, FAILED.';

CREATE INDEX IF NOT EXISTS ix_scraping_crawl_jobs_source_id ON scraping.crawl_jobs (source_id);
CREATE INDEX IF NOT EXISTS ix_scraping_crawl_jobs_status ON scraping.crawl_jobs (status);
CREATE INDEX IF NOT EXISTS ix_scraping_crawl_jobs_started_at ON scraping.crawl_jobs (started_at DESC);

CREATE TABLE IF NOT EXISTS scraping.keywords (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_id   UUID         NOT NULL REFERENCES core.stocks (stock_id) ON DELETE CASCADE,
    keyword    VARCHAR(512) NOT NULL,
    priority   INTEGER      NOT NULL DEFAULT 1,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_scraping_keywords_stock_keyword UNIQUE (stock_id, keyword)
);

COMMENT ON COLUMN scraping.keywords.stock_id IS 'Reference to core.stocks.';
COMMENT ON COLUMN scraping.keywords.keyword IS 'Expanded keyword for news scraping.';

CREATE INDEX IF NOT EXISTS ix_scraping_keywords_stock_id ON scraping.keywords (stock_id);
CREATE INDEX IF NOT EXISTS ix_scraping_keywords_active ON scraping.keywords (is_active, priority DESC);

CREATE TABLE IF NOT EXISTS core.article_metadata (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id    UUID        NOT NULL REFERENCES scraping.sources (id),
    crawl_job_id UUID        NOT NULL REFERENCES scraping.crawl_jobs (id),

    url          TEXT        NOT NULL,
    url_hash     VARCHAR(64) NOT NULL UNIQUE,
    title        TEXT        NOT NULL,
    summary      TEXT,

    published_at TIMESTAMPTZ,
    scraped_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    json_path    TEXT        NOT NULL,
    status       VARCHAR(16),

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN core.article_metadata.source_id IS 'Reference to scraping.sources.';
COMMENT ON COLUMN core.article_metadata.crawl_job_id IS 'Reference to scraping.crawl_jobs.';
COMMENT ON COLUMN core.article_metadata.json_path IS 'Path to the article JSON file on ADLS.';
COMMENT ON COLUMN core.article_metadata.status IS 'METADATA_ONLY, CONTENT_DONE, FAILED.';

CREATE INDEX IF NOT EXISTS ix_core_article_metadata_source_id ON core.article_metadata (source_id);
CREATE INDEX IF NOT EXISTS ix_core_article_metadata_crawl_job_id ON core.article_metadata (crawl_job_id);
CREATE INDEX IF NOT EXISTS ix_core_article_metadata_published_at ON core.article_metadata (published_at);
CREATE INDEX IF NOT EXISTS ix_core_article_metadata_status ON core.article_metadata (status);

CREATE TABLE IF NOT EXISTS core.article_stock_mapping (
    article_id      UUID          NOT NULL REFERENCES core.article_metadata (id) ON DELETE CASCADE,
    stock_id        UUID          NOT NULL REFERENCES core.stocks (stock_id) ON DELETE CASCADE,
    matched_keyword VARCHAR(512),
    confidence      NUMERIC(5, 4),
    PRIMARY KEY (article_id, stock_id)
);

CREATE INDEX IF NOT EXISTS ix_core_article_stock_mapping_stock_id ON core.article_stock_mapping (stock_id);

CREATE TABLE IF NOT EXISTS scraping.crawl_logs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID        NOT NULL REFERENCES scraping.crawl_jobs (id) ON DELETE CASCADE,
    proxy_id         UUID        REFERENCES scraping.proxies (id),

    target_url       TEXT        NOT NULL,
    method           VARCHAR(16) NOT NULL DEFAULT 'GET',

    status_code      INTEGER,
    response_time_ms INTEGER,

    is_success       BOOLEAN,
    error_category   VARCHAR(32),
    error_message    TEXT,

    raw_response_path TEXT,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN scraping.crawl_logs.error_category IS 'TIMEOUT, CAPTCHA, PARSE_ERROR, NETWORK, RATE_LIMIT.';
COMMENT ON COLUMN scraping.crawl_logs.raw_response_path IS 'ADLS path to failed raw HTML for debugging.';

CREATE INDEX IF NOT EXISTS ix_scraping_crawl_logs_job_id ON scraping.crawl_logs (job_id);
CREATE INDEX IF NOT EXISTS ix_scraping_crawl_logs_proxy_id ON scraping.crawl_logs (proxy_id);
CREATE INDEX IF NOT EXISTS ix_scraping_crawl_logs_created_at ON scraping.crawl_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_scraping_crawl_logs_success ON scraping.crawl_logs (is_success);

CREATE TABLE IF NOT EXISTS scraping.scrape_checkpoints (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name         VARCHAR(64) NOT NULL,
    ticker              VARCHAR(16) NOT NULL,
    keyword             TEXT        NOT NULL,
    keyword_id          UUID,
    run_key             TEXT        NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    last_page_completed INTEGER     NOT NULL DEFAULT 0,
    pages_crawled       INTEGER     NOT NULL DEFAULT 0,
    articles_found      INTEGER     NOT NULL DEFAULT 0,
    articles_persisted  INTEGER     NOT NULL DEFAULT 0,
    articles_skipped    INTEGER     NOT NULL DEFAULT 0,
    errors_count        INTEGER     NOT NULL DEFAULT 0,
    last_error_category VARCHAR(64),
    last_error_message  TEXT,
    last_started_at     TIMESTAMPTZ,
    last_completed_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_scrape_checkpoints_natural UNIQUE (source_name, ticker, keyword, run_key)
);

COMMENT ON TABLE scraping.scrape_checkpoints IS 'Per source/ticker/keyword resume state for scraper retries.';
COMMENT ON COLUMN scraping.scrape_checkpoints.run_key IS 'Deterministic resume scope. Defaults to current date plus run shape unless explicitly overridden.';
COMMENT ON COLUMN scraping.scrape_checkpoints.status IS 'PENDING, RUNNING, COMPLETED, FAILED.';
COMMENT ON COLUMN scraping.scrape_checkpoints.last_page_completed IS 'Deepest listing page fully processed for this source/ticker/keyword/run_key.';

CREATE INDEX IF NOT EXISTS ix_scrape_checkpoints_run_key ON scraping.scrape_checkpoints (run_key);
CREATE INDEX IF NOT EXISTS ix_scrape_checkpoints_status ON scraping.scrape_checkpoints (status);
CREATE INDEX IF NOT EXISTS ix_scrape_checkpoints_updated_at ON scraping.scrape_checkpoints (updated_at DESC);

-- =============================================================================
-- SCHEMA: RAG (CDC medallion processing checkpoints)
-- =============================================================================

CREATE TABLE IF NOT EXISTS rag.cdc_file_processing_checkpoints (
    article_id          UUID        PRIMARY KEY,
    event_key           TEXT        NOT NULL,
    source_id           UUID,
    crawl_job_id        UUID,
    url                 TEXT        NOT NULL,
    url_hash            VARCHAR(64),
    json_path           TEXT        NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
    bronze_document     JSONB,
    silver_document     JSONB,
    qdrant_points       INTEGER     NOT NULL DEFAULT 0,
    attempts            INTEGER     NOT NULL DEFAULT 0,
    last_error          TEXT,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    bronze_completed_at TIMESTAMPTZ,
    silver_completed_at TIMESTAMPTZ,
    gold_completed_at   TIMESTAMPTZ,
    failed_at           TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE rag.cdc_file_processing_checkpoints IS 'Per article file CDC medallion state from Debezium event to Qdrant upsert.';
COMMENT ON COLUMN rag.cdc_file_processing_checkpoints.status IS 'RECEIVED, PROCESSING, BRONZE_DONE, SILVER_DONE, GOLD_DONE, FAILED.';
COMMENT ON COLUMN rag.cdc_file_processing_checkpoints.bronze_document IS 'Raw normalized article document read from MinIO or ADLS.';
COMMENT ON COLUMN rag.cdc_file_processing_checkpoints.silver_document IS 'Cleaned article document after text normalization and quality checks.';
COMMENT ON COLUMN rag.cdc_file_processing_checkpoints.qdrant_points IS 'Number of vector chunks successfully upserted into Qdrant.';

CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_status ON rag.cdc_file_processing_checkpoints (status);
CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_updated_at ON rag.cdc_file_processing_checkpoints (updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_json_path ON rag.cdc_file_processing_checkpoints (json_path);

-- -----------------------------------------------------------------------------
-- updated_at trigger for core.article_metadata
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_article_metadata_updated_at ON core.article_metadata;
CREATE TRIGGER trg_article_metadata_updated_at
    BEFORE UPDATE ON core.article_metadata
    FOR EACH ROW
    EXECUTE FUNCTION core.set_updated_at();

DO $$
BEGIN
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA scraping TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA rag TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA core TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA scraping TO %I', current_user);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA rag TO %I', current_user);
END
$$;
