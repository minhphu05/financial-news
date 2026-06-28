-- =============================================================================
-- Financial News Scraper — normalized metadata schema
-- =============================================================================
-- Target database : ${METADATA_POSTGRES_DB}  (default: financial_metadata)
-- Schema          : public
--
-- This script is idempotent: it can be applied to a fresh volume (picked up
-- automatically by the postgres entrypoint) OR run manually against a running
-- container, e.g.:
--
--   docker compose exec -T postgresql \
--     psql -U "$METADATA_POSTGRES_USER" -d "$METADATA_POSTGRES_DB" \
--     < docker/postgresql/init-scripts/003-create-scraper-schema.sql
--
-- Article *content* lives as JSON files in ADLS (financialnews-datalake);
-- only metadata is stored here. `article_metadata.json_path` points to the
-- raw JSON blob.
-- =============================================================================

-- gen_random_uuid() lives in pgcrypto.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- stock — VN30 universe
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock (
    stock_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker       VARCHAR(16)  NOT NULL UNIQUE,
    company_name VARCHAR(512) NOT NULL,
    exchange     VARCHAR(16),                       -- HOSE, HNX, UPCOM
    sector       VARCHAR(128),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- keyword — search terms mapped to a stock
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS keyword (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_id   UUID         NOT NULL REFERENCES stock (stock_id) ON DELETE CASCADE,
    keyword    VARCHAR(512) NOT NULL,
    priority   INTEGER      NOT NULL DEFAULT 1,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_keyword_stock UNIQUE (stock_id, keyword)
);

CREATE INDEX IF NOT EXISTS ix_keyword_stock_id ON keyword (stock_id);

-- -----------------------------------------------------------------------------
-- source — news websites being crawled
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source (
    id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name      VARCHAR(64)  NOT NULL UNIQUE,
    base_url  VARCHAR(512),
    country   VARCHAR(64),
    language  VARCHAR(16),
    is_active BOOLEAN      NOT NULL DEFAULT TRUE
);

-- -----------------------------------------------------------------------------
-- crawl_job — one row per pipeline execution
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_job (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(16) NOT NULL DEFAULT 'RUNNING',   -- RUNNING, SUCCESS, FAILED
    crawler_version VARCHAR(32),
    note            TEXT
);

-- -----------------------------------------------------------------------------
-- article_metadata — one row per scraped article
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_metadata (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    source_id        UUID        NOT NULL REFERENCES source (id),
    crawl_job_id     UUID        NOT NULL REFERENCES crawl_job (id),

    url              TEXT        NOT NULL,
    url_hash         VARCHAR(64) NOT NULL UNIQUE,             -- sha256 of canonical URL

    title            TEXT        NOT NULL,
    summary          TEXT,

    tag              VARCHAR(128),
    type             VARCHAR(128),

    author           VARCHAR(256),
    language         VARCHAR(16),

    published_at     TIMESTAMPTZ,
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    json_path        TEXT,                                    -- ADLS path to raw JSON

    has_content      BOOLEAN     NOT NULL DEFAULT FALSE,

    content_checksum VARCHAR(64),                             -- sha256 of content body
    content_version  INTEGER     NOT NULL DEFAULT 1,

    status           VARCHAR(16) NOT NULL DEFAULT 'METADATA_ONLY',  -- METADATA_ONLY, CONTENT_DONE, FAILED

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_article_metadata_source_id    ON article_metadata (source_id);
CREATE INDEX IF NOT EXISTS ix_article_metadata_crawl_job_id ON article_metadata (crawl_job_id);
CREATE INDEX IF NOT EXISTS ix_article_metadata_published_at ON article_metadata (published_at);
CREATE INDEX IF NOT EXISTS ix_article_metadata_status       ON article_metadata (status);

-- -----------------------------------------------------------------------------
-- article_stock — bridge between articles and stocks
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_stock (
    article_id      UUID         NOT NULL REFERENCES article_metadata (id) ON DELETE CASCADE,
    stock_id        UUID         NOT NULL REFERENCES stock (stock_id) ON DELETE CASCADE,
    matched_keyword VARCHAR(512),
    confidence      NUMERIC(5, 4),
    PRIMARY KEY (article_id, stock_id)
);

CREATE INDEX IF NOT EXISTS ix_article_stock_stock_id ON article_stock (stock_id);

-- -----------------------------------------------------------------------------
-- crawl_log — per (job, source, keyword) crawl outcome
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    job_id        UUID        REFERENCES crawl_job (id) ON DELETE CASCADE,
    source_id     UUID        REFERENCES source (id),
    keyword_id    UUID        REFERENCES keyword (id),

    status        VARCHAR(16) NOT NULL,                       -- SUCCESS, FAILED

    duration_ms   INTEGER,
    article_found INTEGER     NOT NULL DEFAULT 0,
    error_message TEXT,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_crawl_log_job_id ON crawl_log (job_id);

-- -----------------------------------------------------------------------------
-- updated_at trigger for article_metadata
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_article_metadata_updated_at ON article_metadata;
CREATE TRIGGER trg_article_metadata_updated_at
    BEFORE UPDATE ON article_metadata
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
