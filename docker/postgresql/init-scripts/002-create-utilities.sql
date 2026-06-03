-- =====================================================================
-- Financial News RAG Stack - Database Utilities and Views
-- =====================================================================
-- 
-- This script creates useful views and utility functions for 
-- monitoring and managing the RAG metadata database.
--
-- =====================================================================

SET search_path TO rag_metadata, public;


-- =====================================================================
-- Materialized View: Articles Processing Summary
-- =====================================================================
-- Provides quick summary of article processing status

CREATE MATERIALIZED VIEW IF NOT EXISTS articles_processing_summary AS
SELECT
    processing_status,
    COUNT(*) as article_count,
    COUNT(CASE WHEN is_valid THEN 1 END) as valid_articles,
    COUNT(CASE WHEN is_valid = false THEN 1 END) as invalid_articles,
    MIN(created_at) as oldest_article,
    MAX(created_at) as newest_article,
    ROUND(100.0 * COUNT(CASE WHEN is_valid THEN 1 END) / COUNT(*), 2) as validity_percentage
FROM articles
GROUP BY processing_status
ORDER BY article_count DESC;

CREATE INDEX idx_articles_status_summary ON articles_processing_summary(processing_status);


-- =====================================================================
-- Materialized View: Embedding Coverage
-- =====================================================================
-- Shows which articles have embeddings and which don't

CREATE MATERIALIZED VIEW IF NOT EXISTS embedding_coverage AS
SELECT
    e.model_name,
    e.embedding_type,
    COUNT(DISTINCT e.article_id) as embedded_articles,
    (SELECT COUNT(*) FROM articles WHERE processing_status = 'completed') as total_completed,
    ROUND(100.0 * COUNT(DISTINCT e.article_id) / 
          (SELECT COUNT(*) FROM articles WHERE processing_status = 'completed'), 2) as coverage_percentage
FROM embeddings e
GROUP BY e.model_name, e.embedding_type
ORDER BY e.model_name, e.embedding_type;


-- =====================================================================
-- Materialized View: NER Statistics
-- =====================================================================
-- Shows entity type distribution and validation status

CREATE MATERIALIZED VIEW IF NOT EXISTS ner_statistics AS
SELECT
    entity_type,
    COUNT(*) as total_entities,
    COUNT(CASE WHEN is_validated THEN 1 END) as validated_entities,
    COUNT(CASE WHEN is_validated = false THEN 1 END) as unvalidated_entities,
    COUNT(DISTINCT article_id) as articles_with_entities,
    ROUND(AVG(COALESCE(entity_confidence, 0))::numeric, 4) as avg_confidence,
    ROUND(100.0 * COUNT(CASE WHEN is_validated THEN 1 END) / COUNT(*), 2) as validation_percentage
FROM ner_labels
GROUP BY entity_type
ORDER BY total_entities DESC;


-- =====================================================================
-- View: Articles Without Embeddings
-- =====================================================================
-- Find articles that have been processed but don't have embeddings

CREATE OR REPLACE VIEW articles_without_embeddings AS
SELECT
    a.article_id,
    a.external_id,
    a.title,
    a.source_name,
    a.published_date,
    a.processing_status,
    COALESCE(e.embedding_count, 0) as embedding_count
FROM articles a
LEFT JOIN (
    SELECT article_id, COUNT(*) as embedding_count
    FROM embeddings
    GROUP BY article_id
) e ON a.article_id = e.article_id
WHERE a.processing_status = 'completed' AND e.embedding_count = 0
ORDER BY a.created_at DESC;


-- =====================================================================
-- View: Processing Performance
-- =====================================================================
-- Analyze processing efficiency and performance metrics

CREATE OR REPLACE VIEW processing_performance AS
SELECT
    event_type,
    event_status,
    COUNT(*) as event_count,
    ROUND(AVG(COALESCE(processing_time_ms, 0))::numeric, 2) as avg_time_ms,
    MAX(processing_time_ms) as max_time_ms,
    MIN(processing_time_ms) as min_time_ms,
    ROUND(AVG(COALESCE(items_processed, 0))::numeric, 2) as avg_items_processed
FROM processing_events
GROUP BY event_type, event_status
ORDER BY event_type, event_count DESC;


-- =====================================================================
-- View: Dataset Composition
-- =====================================================================
-- Shows detailed composition of each dataset

CREATE OR REPLACE VIEW dataset_composition AS
SELECT
    d.dataset_id,
    d.dataset_name,
    d.dataset_type,
    d.version,
    COUNT(DISTINCT dm.article_id) as member_count,
    COUNT(DISTINCT CASE WHEN sp.split_type = 'train' THEN dm.article_id END) as train_count,
    COUNT(DISTINCT CASE WHEN sp.split_type = 'val' THEN dm.article_id END) as val_count,
    COUNT(DISTINCT CASE WHEN sp.split_type = 'test' THEN dm.article_id END) as test_count,
    d.created_at
FROM datasets d
LEFT JOIN dataset_members dm ON d.dataset_id = dm.dataset_id
LEFT JOIN dataset_members sp ON dm.member_id = sp.member_id
GROUP BY d.dataset_id, d.dataset_name, d.dataset_type, d.version, d.created_at
ORDER BY d.created_at DESC;


-- =====================================================================
-- Function: Get Article with All Related Data
-- =====================================================================
-- Retrieves complete data for an article (metadata, embeddings, entities)

CREATE OR REPLACE FUNCTION get_article_complete_data(article_id_param BIGINT)
RETURNS TABLE (
    article_id BIGINT,
    external_id VARCHAR,
    title VARCHAR,
    content TEXT,
    source_name VARCHAR,
    published_date TIMESTAMP,
    processing_status VARCHAR,
    embedding_count INT,
    ner_label_count INT,
    span_count INT
) AS $$
SELECT
    a.article_id,
    a.external_id,
    a.title,
    a.content,
    a.source_name,
    a.published_date,
    a.processing_status,
    COALESCE(COUNT(DISTINCT e.embedding_id), 0)::INT as embedding_count,
    COALESCE(COUNT(DISTINCT ner.ner_id), 0)::INT as ner_label_count,
    COALESCE(COUNT(DISTINCT sp.span_id), 0)::INT as span_count
FROM articles a
LEFT JOIN embeddings e ON a.article_id = e.article_id
LEFT JOIN ner_labels ner ON a.article_id = ner.article_id
LEFT JOIN extraction_spans sp ON a.article_id = sp.article_id
WHERE a.article_id = article_id_param
GROUP BY a.article_id, a.external_id, a.title, a.content, a.source_name, a.published_date, a.processing_status;
$$ LANGUAGE SQL;


-- =====================================================================
-- Function: Calculate Dataset Statistics
-- =====================================================================
-- Calculates comprehensive statistics for a dataset

CREATE OR REPLACE FUNCTION get_dataset_statistics(dataset_name_param VARCHAR)
RETURNS TABLE (
    total_articles INT,
    articles_with_embeddings INT,
    articles_with_ner INT,
    articles_with_spans INT,
    avg_embeddings_per_article NUMERIC,
    avg_entities_per_article NUMERIC,
    validation_percentage NUMERIC
) AS $$
SELECT
    COUNT(DISTINCT dm.article_id)::INT as total_articles,
    COUNT(DISTINCT CASE WHEN e.embedding_id IS NOT NULL THEN dm.article_id END)::INT as articles_with_embeddings,
    COUNT(DISTINCT CASE WHEN ner.ner_id IS NOT NULL THEN dm.article_id END)::INT as articles_with_ner,
    COUNT(DISTINCT CASE WHEN sp.span_id IS NOT NULL THEN dm.article_id END)::INT as articles_with_spans,
    ROUND(COUNT(DISTINCT e.embedding_id)::NUMERIC / NULLIF(COUNT(DISTINCT dm.article_id), 0), 2) as avg_embeddings_per_article,
    ROUND(COUNT(DISTINCT ner.ner_id)::NUMERIC / NULLIF(COUNT(DISTINCT dm.article_id), 0), 2) as avg_entities_per_article,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN ner.is_validated THEN ner.ner_id END)::NUMERIC / 
          NULLIF(COUNT(DISTINCT ner.ner_id), 0), 2) as validation_percentage
FROM datasets d
JOIN dataset_members dm ON d.dataset_id = dm.dataset_id
LEFT JOIN embeddings e ON dm.article_id = e.article_id
LEFT JOIN ner_labels ner ON dm.article_id = ner.article_id
LEFT JOIN extraction_spans sp ON dm.article_id = sp.article_id
WHERE d.dataset_name = dataset_name_param
GROUP BY d.dataset_id;
$$ LANGUAGE SQL;


-- =====================================================================
-- Function: Find Similar Articles
-- =====================================================================
-- Uses embeddings to find similar articles (requires pgvector extension)
-- Note: This example uses array distance; for production, install pgvector

CREATE OR REPLACE FUNCTION find_similar_articles(
    article_id_param BIGINT,
    limit_count INT DEFAULT 5
)
RETURNS TABLE (
    similar_article_id BIGINT,
    similarity_score FLOAT
) AS $$
SELECT
    e2.article_id,
    (SELECT 1.0 - (sqrt(sum((a-b)^2))) / sqrt(2) 
     FROM (SELECT unnest(e1.embedding_vector) as a, unnest(e2.embedding_vector) as b) t)::FLOAT as similarity
FROM embeddings e1
JOIN embeddings e2 ON e1.embedding_type = e2.embedding_type 
    AND e1.model_name = e2.model_name
    AND e2.article_id != article_id_param
WHERE e1.article_id = article_id_param
ORDER BY similarity DESC
LIMIT limit_count;
$$ LANGUAGE SQL;


-- =====================================================================
-- Function: Get Processing Timeline
-- =====================================================================
-- Shows processing timeline for an article

CREATE OR REPLACE FUNCTION get_article_processing_timeline(article_id_param BIGINT)
RETURNS TABLE (
    event_order INT,
    event_type VARCHAR,
    event_status VARCHAR,
    processor_name VARCHAR,
    event_timestamp TIMESTAMP,
    processing_time_ms INT,
    result_message TEXT
) AS $$
SELECT
    ROW_NUMBER() OVER (ORDER BY event_timestamp ASC)::INT as event_order,
    event_type,
    event_status,
    processor_name,
    event_timestamp,
    processing_time_ms,
    result_message
FROM processing_events
WHERE article_id = article_id_param
ORDER BY event_timestamp ASC;
$$ LANGUAGE SQL;


-- =====================================================================
-- Procedure: Archive Old Articles
-- =====================================================================
-- Archives articles older than a specified date

CREATE OR REPLACE FUNCTION archive_old_articles(days_threshold INT DEFAULT 365)
RETURNS TABLE (
    archived_count INT
) AS $$
DECLARE
    v_archived_count INT;
BEGIN
    UPDATE articles
    SET processing_status = 'archived'
    WHERE created_at < CURRENT_TIMESTAMP - (days_threshold || ' days')::INTERVAL
        AND processing_status != 'archived';
    
    GET DIAGNOSTICS v_archived_count = ROW_COUNT;
    
    RETURN QUERY SELECT v_archived_count;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- Procedure: Clean Unvalidated Entities
-- =====================================================================
-- Removes unvalidated NER entities older than specified date

CREATE OR REPLACE FUNCTION clean_unvalidated_entities(days_threshold INT DEFAULT 90)
RETURNS TABLE (
    deleted_count INT
) AS $$
DECLARE
    v_deleted_count INT;
BEGIN
    DELETE FROM ner_labels
    WHERE is_validated = false
        AND created_at < CURRENT_TIMESTAMP - (days_threshold || ' days')::INTERVAL;
    
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    
    RETURN QUERY SELECT v_deleted_count;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- Procedure: Update Dataset Statistics
-- =====================================================================
-- Recalculates and updates dataset statistics

CREATE OR REPLACE FUNCTION update_dataset_statistics(dataset_id_param BIGINT)
RETURNS void AS $$
BEGIN
    UPDATE datasets
    SET
        total_articles = (SELECT COUNT(*) FROM dataset_members WHERE dataset_id = dataset_id_param),
        created_articles = (SELECT COUNT(*) FROM dataset_members dm 
                           JOIN articles a ON dm.article_id = a.article_id 
                           WHERE dm.dataset_id = dataset_id_param AND a.is_valid = true),
        labeled_articles = (SELECT COUNT(DISTINCT article_id) FROM ner_labels 
                           WHERE article_id IN (
                               SELECT article_id FROM dataset_members WHERE dataset_id = dataset_id_param
                           )),
        annotated_articles = (SELECT COUNT(DISTINCT article_id) FROM extraction_spans 
                             WHERE article_id IN (
                                 SELECT article_id FROM dataset_members WHERE dataset_id = dataset_id_param
                             )),
        updated_at = CURRENT_TIMESTAMP
    WHERE dataset_id = dataset_id_param;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- Grant Permissions on Views and Functions
-- =====================================================================

GRANT SELECT ON ALL MATERIALIZED VIEWS IN SCHEMA rag_metadata TO rag_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA rag_metadata TO rag_readonly;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA rag_metadata TO rag_readonly;


-- =====================================================================
-- Database Utilities Initialization Complete
-- =====================================================================

\echo '=========================================='
\echo 'RAG Metadata Utilities Created'
\echo '=========================================='
\echo 'Materialized Views:'
\echo '  - articles_processing_summary'
\echo '  - embedding_coverage'
\echo '  - ner_statistics'
\echo 'Views:'
\echo '  - articles_without_embeddings'
\echo '  - processing_performance'
\echo '  - dataset_composition'
\echo 'Functions:'
\echo '  - get_article_complete_data()'
\echo '  - get_dataset_statistics()'
\echo '  - find_similar_articles()'
\echo '  - get_article_processing_timeline()'
\echo '  - archive_old_articles()'
\echo '  - clean_unvalidated_entities()'
\echo '  - update_dataset_statistics()'
\echo '=========================================='
