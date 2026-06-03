# =====================================================================
# PostgreSQL 17 Container for Metadata Storage
# =====================================================================
#
# This container stores application metadata and processed data.
# Used for RAG system metadata, embeddings, and analytics data.
#
# Features:
# - Built on official PostgreSQL 17 image
# - Configurable performance tuning parameters
# - Health check support
# - Volume persistence
# - Custom initialization scripts support
#
# Environment Variables:
# - POSTGRES_USER: Database superuser
# - POSTGRES_PASSWORD: Superuser password
# - POSTGRES_DB: Initial database to create
# - SHARED_BUFFERS: Memory for caching (recommended: 25% of RAM)
# - EFFECTIVE_CACHE_SIZE: Memory available to PostgreSQL (recommended: 75% of RAM)
# - WORK_MEM: Memory per operation (in MB)
# - MAINTENANCE_WORK_MEM: Memory for maintenance operations (in MB)
# - MAX_CONNECTIONS: Maximum simultaneous connections
#
# =====================================================================

FROM postgres:17

# Set environment variables for PostgreSQL configuration
ENV POSTGRES_INITDB_ARGS="-c shared_buffers=64MB -c effective_cache_size=256MB -c work_mem=4MB -c maintenance_work_mem=64MB"

# Create scripts directory for initialization
RUN mkdir -p /docker-entrypoint-initdb.d

# Copy custom initialization scripts (if any exist)
# COPY ./docker/postgresql/init-scripts/ /docker-entrypoint-initdb.d/

# Expose PostgreSQL default port
EXPOSE 5432

# Health check configuration
# Checks if PostgreSQL is ready to accept connections
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}

# Default command (inherited from postgres:17-alpine base image)
# CMD ["postgres"]