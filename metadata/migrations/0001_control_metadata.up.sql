CREATE SCHEMA IF NOT EXISTS control_metadata;

CREATE OR REPLACE FUNCTION control_metadata.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TABLE control_metadata.news_sources (
    source_id varchar(128) PRIMARY KEY,
    source_name varchar(255) NOT NULL CHECK (btrim(source_name) <> ''),
    source_type varchar(64) NOT NULL CHECK (btrim(source_type) <> ''),
    enabled boolean NOT NULL DEFAULT true,
    base_url text,
    description text,
    config jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE control_metadata.pipeline_configs (
    config_id varchar(128) PRIMARY KEY,
    pipeline_name varchar(128) NOT NULL CHECK (btrim(pipeline_name) <> ''),
    source_id varchar(128) NOT NULL REFERENCES control_metadata.news_sources(source_id) ON DELETE RESTRICT,
    enabled boolean NOT NULL DEFAULT true,
    config_version integer NOT NULL DEFAULT 1 CHECK (config_version > 0),
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parameters) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pipeline_name, source_id)
);

CREATE TRIGGER news_sources_set_updated_at
BEFORE UPDATE ON control_metadata.news_sources
FOR EACH ROW EXECUTE FUNCTION control_metadata.set_updated_at();

CREATE TRIGGER pipeline_configs_set_updated_at
BEFORE UPDATE ON control_metadata.pipeline_configs
FOR EACH ROW EXECUTE FUNCTION control_metadata.set_updated_at();

ALTER TABLE control_metadata.news_sources REPLICA IDENTITY FULL;
ALTER TABLE control_metadata.pipeline_configs REPLICA IDENTITY FULL;
