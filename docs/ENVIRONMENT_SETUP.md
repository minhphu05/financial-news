# Financial News RAG Stack - Environment Setup Guide

## Overview

This document describes the environment configuration and setup for the Financial News RAG (Retrieval-Augmented Generation) Stack. The stack consists of multiple interconnected services orchestrated via Docker Compose.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Financial News RAG Stack                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐                      │
│  │    MongoDB 8.0   │  │   PostgreSQL 14  │                      │
│  │  (Article Store) │  │  (Prefect Metadata)                     │
│  └──────────────────┘  └──────────────────┘                      │
│         ▲                       ▲                                 │
│         │                       │                                 │
│  ┌──────────────────────────────────────────┐                   │
│  │     Prefect Orchestration Platform       │                   │
│  │  - Prefect Server (port 4200)            │                   │
│  │  - Prefect Services                      │                   │
│  │  - Prefect Worker (runs scraper flows)   │                   │
│  └──────────────────────────────────────────┘                   │
│         ▲                                                         │
│         │                                                         │
│  ┌──────────────────┐  ┌──────────────────┐                      │
│  │  Redis 7         │  │  MLflow 3.10     │                      │
│  │  (Cache & Queue) │  │  (Experiment Tracking)                  │
│  └──────────────────┘  └──────────────────┘                      │
│                                                                   │
│  ┌──────────────────────────────────────────┐                   │
│  │    PostgreSQL 17 - Metadata Storage       │ ← NEW             │
│  │  - Article metadata & embeddings          │                   │
│  │  - NER labels and annotations             │                   │
│  │  - Processing status & analytics          │                   │
│  └──────────────────────────────────────────┘                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Services Description

### 1. **MongoDB 8.0** (Document Store)
- **Purpose**: Stores raw and processed financial news articles
- **Port**: 27017 (exposed as 27018)
- **Volumes**: `./data` directory mounted to `/data/db`
- **Network**: `vifinner-net`
- **Environment Variables**:
  - `MONGO_USER`: Admin username
  - `MONGO_PASSWORD`: Admin password

### 2. **PostgreSQL 14 - Prefect** (Orchestration Database)
- **Purpose**: Stores Prefect workflow metadata and execution history
- **Port**: 5432 (exposed as 5433)
- **Volumes**: `postgres_data` named volume
- **Network**: `financial-net`
- **Database**: `prefectdb`
- **Environment Variables**:
  - `PF_POSTGRES_USER`: Prefect database user
  - `PF_POSTGRES_PASSWORD`: Prefect database password

### 3. **PostgreSQL 17 - Metadata Storage** (NEW)
- **Purpose**: Stores application metadata, embeddings, and processed data
- **Port**: 5432 (exposed as 5434)
- **Volumes**: `metadata_postgres_data` named volume
- **Network**: `financial-net`
- **Database**: `financial_metadata`
- **Features**:
  - Alpine-based image (lightweight)
  - Performance-tuned for metadata workloads
  - Configurable shared buffers and cache
  - Health checks enabled
- **Environment Variables**:
  - `METADATA_POSTGRES_USER`: Metadata database user
  - `METADATA_POSTGRES_PASSWORD`: Metadata database password
  - `METADATA_POSTGRES_SHARED_BUFFERS`: Memory for caching
  - `METADATA_POSTGRES_MAX_CONNECTIONS`: Connection pool size

### 4. **Redis 7** (Cache & Message Broker)
- **Purpose**: Caching and message brokering for Prefect
- **Port**: 6379
- **Volumes**: `redis_data` named volume
- **Network**: `financial-net`
- **Features**:
  - AOF persistence enabled
  - Health checks enabled

### 5. **MLflow 3.10** (Experiment Tracking)
- **Purpose**: Tracks ML experiments, models, and metrics
- **Port**: 5000
- **Volumes**:
  - `mlflow_store`: Backend storage
  - `mlflow_artifacts`: Artifact storage
- **Network**: `financial-net`
- **Backend**: SQLite (located in `/mlflow/store/mlflow.db`)

### 6. **Prefect Server** (Workflow Orchestration)
- **Purpose**: Central orchestration server for workflows
- **Port**: 4200
- **Network**: `financial-net`
- **Dependencies**: PostgreSQL 14, Redis 7

### 7. **Prefect Services** (Orchestration Services)
- **Purpose**: Background services for Prefect (notifications, cleanup, etc.)
- **Network**: `financial-net`
- **Dependencies**: Prefect Server

### 8. **Prefect Worker** (Flow Execution)
- **Purpose**: Executes data scraping and ingestion flows
- **Image**: Built from `docker/ingestion/Dockerfile`
- **Environment**: Loads from `.env` file
- **Network**: `financial-net`
- **Dependencies**: Prefect Server

---

## Environment Variables Reference

### General Configuration
```bash
APP_ENV=development              # Application environment
APP_NAME=financial-news-rag      # Application identifier
LOG_LEVEL=INFO                   # Logging level
```

### MongoDB Configuration
```bash
MONGO_USER=admin                 # Root username
MONGO_PASSWORD=admin             # Root password
MONGO_PORT=27017                 # Internal port
MONGO_DB_RAW=financial_news_raw   # Raw articles database
MONGO_DB_PROCESSED=financial_news_processed  # Processed articles database
```

### PostgreSQL - Prefect Configuration
```bash
PF_POSTGRES_USER=prefect              # Database user
PF_POSTGRES_PASSWORD=prefect          # Database password
PF_POSTGRES_DB=prefectdb              # Database name
PF_POSTGRES_INTERNAL_PORT=5432        # Internal port
PF_POSTGRES_EXTERNAL_PORT=5432        # External/host port
PF_POSTGRES_HOST=posgresql-prefect    # Service hostname
```

### PostgreSQL - Metadata Configuration
```bash
METADATA_POSTGRES_USER=metadata_user              # Database user
METADATA_POSTGRES_PASSWORD=metadata_password      # Database password
METADATA_POSTGRES_DB=financial_metadata           # Database name
METADATA_POSTGRES_INTERNAL_PORT=5432              # Internal port
METADATA_POSTGRES_EXTERNAL_PORT=5434              # External/host port
METADATA_POSTGRES_HOST=postgresql                 # Service hostname
METADATA_POSTGRES_VERSION=17                      # PostgreSQL version
METADATA_POSTGRES_SHARED_BUFFERS=64MB             # Memory for caching
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=256MB      # Total cache size
METADATA_POSTGRES_WORK_MEM=4MB                    # Per-operation memory
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=64MB       # Maintenance memory
METADATA_POSTGRES_MAX_CONNECTIONS=100             # Connection pool size
```

### Redis Configuration
```bash
REDIS_HOST=redis-prefect         # Service hostname
REDIS_PORT=6379                  # Redis port
REDIS_MESSAGING_DB=0             # Messaging database index
REDIS_CACHE_DB=1                 # Cache database index
REDIS_PASSWORD=                  # Password (empty by default)
```

### MLflow Configuration
```bash
MLFLOW_HOST=mlflow               # Service hostname
MLFLOW_PORT=5000                 # MLflow port
MLFLOW_ARTIFACT_PATH=/mlflow/artifacts
MLFLOW_BACKEND_STORE=/mlflow/store
MLFLOW_TRACKING_URI=http://mlflow:5000
```

### Prefect Configuration
```bash
PREFECT_SERVER_HOST=prefect-server
PREFECT_SERVER_PORT=4200
PREFECT_API_URL=http://prefect-server:4200/api
PREFECT_SQLALCHEMY_POOL_SIZE=20
PREFECT_SQLALCHEMY_MAX_OVERFLOW=10
PREFECT_RUNS_RETENTION_DAYS=30
PREFECT_LOGGING_LEVEL=INFO
```

### Data Ingestion Configuration
```bash
SCRAPER_TIMEOUT=30               # Request timeout in seconds
SCRAPER_MAX_RETRIES=3            # Retry attempts
SCRAPER_DELAY=1                  # Delay between requests (seconds)
INGESTION_BATCH_SIZE=100         # Batch processing size
INGESTION_WORKERS=4              # Number of worker threads
INGESTION_LOG_DIR=./logs/ingestion
```

---

## Setup Instructions

### 1. Clone Configuration Files
```bash
# Copy example configuration to actual .env
cp .env.example .env
```

### 2. Review and Update .env
Edit `.env` file and update values according to your environment:

**For Development:**
```bash
APP_ENV=development
LOG_LEVEL=DEBUG
DEBUG=true
METADATA_POSTGRES_SHARED_BUFFERS=32MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=128MB
```

**For Production:**
```bash
APP_ENV=production
LOG_LEVEL=WARNING
DEBUG=false
METADATA_POSTGRES_SHARED_BUFFERS=4GB        # Adjust based on available RAM
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=16GB # Usually 75% of RAM
POSTGRES_SSL_MODE=require
JWT_SECRET_KEY=<generate-secure-key>
API_TOKEN=<generate-secure-token>
```

### 3. Start Services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service health
docker-compose ps
```

### 4. Verify Services
```bash
# Test MongoDB connection
mongosh mongodb://admin:admin@localhost:27017/admin

# Test PostgreSQL - Prefect
psql -h localhost -p 5432 -U prefect -d prefectdb

# Test PostgreSQL - Metadata
psql -h localhost -p 5434 -U metadata_user -d financial_metadata

# Test Redis
redis-cli -h localhost -p 6379 ping

# Test MLflow (browser)
# Navigate to http://localhost:5000

# Test Prefect Server (browser)
# Navigate to http://localhost:4200
```

---

## Docker Networks

The stack uses two Docker networks:

### financial-net (Bridge Network)
Connects:
- PostgreSQL 14 (Prefect)
- PostgreSQL 17 (Metadata)
- Redis 7
- MLflow
- Prefect Server
- Prefect Services
- Prefect Worker

### vifinner-net (Bridge Network)
Connects:
- MongoDB 8.0

---

## Volumes Management

### Named Volumes
```bash
postgres_data              # PostgreSQL 14 data (Prefect)
metadata_postgres_data     # PostgreSQL 17 data (Metadata)
redis_data                 # Redis persistent data
mlflow_store               # MLflow backend storage
mlflow_artifacts           # MLflow artifacts storage
```

### Bind Mounts
```bash
./data                     # MongoDB data directory
./logs/ingestion           # Ingestion process logs (auto-created)
```

### View Volumes
```bash
# List all volumes
docker volume ls

# Inspect a volume
docker volume inspect financial-news_metadata_postgres_data

# Remove unused volumes
docker volume prune
```

---

## Database Initialization

### PostgreSQL - Metadata
The PostgreSQL 17 container automatically initializes with:
- Database: `financial_metadata`
- User: `metadata_user`
- Optimized configuration for metadata workloads

**Optional: Custom Initialization Scripts**
Place SQL files in `docker/postgresql/init-scripts/` directory. They will be executed automatically during container initialization.

Example structure:
```
docker/postgresql/init-scripts/
├── 001-create-tables.sql
├── 002-create-indexes.sql
└── 003-seed-data.sql
```

---

## Performance Tuning

### PostgreSQL 17 Metadata Configuration
Adjust these parameters based on your environment:

```bash
# For low-memory environments (development)
METADATA_POSTGRES_SHARED_BUFFERS=64MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=256MB
METADATA_POSTGRES_WORK_MEM=4MB
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=64MB
METADATA_POSTGRES_MAX_CONNECTIONS=50

# For production (adjust based on available RAM)
METADATA_POSTGRES_SHARED_BUFFERS=8GB      # ~25% of total RAM
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=32GB  # ~75% of total RAM
METADATA_POSTGRES_WORK_MEM=64MB           # For larger datasets
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=512MB
METADATA_POSTGRES_MAX_CONNECTIONS=200
```

### Connection Pooling
For high-concurrency scenarios, consider using PgBouncer:
```bash
# Additional service in docker-compose.yml
pgbouncer:
  image: pgbouncer:latest
  environment:
    PGBOUNCER_DATABASES_HOST: postgresql
    PGBOUNCER_DATABASES_PORT: 5432
    PGBOUNCER_POOL_MODE: transaction
    PGBOUNCER_MAX_CLIENT_CONN: 1000
    PGBOUNCER_DEFAULT_POOL_SIZE: 25
```

---

## Security Best Practices

### 1. Secrets Management
Never hardcode sensitive values in `.env`. For production:

**Option A: Environment Variables**
```bash
export METADATA_POSTGRES_PASSWORD=$(aws secretsmanager get-secret-value --secret-id db-password --query SecretString --output text)
docker-compose up -d
```

**Option B: Docker Secrets**
```bash
# Create secret
echo "metadata_password_here" | docker secret create postgres_password -

# Use in docker-compose.yml
services:
  postgresql:
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
```

**Option C: Azure Key Vault / AWS Secrets Manager**
Use specialized tools to inject secrets at runtime.

### 2. Network Security
- Change default passwords for all services
- Use strong passwords (minimum 16 characters, mixed case, numbers, symbols)
- Disable unnecessary ports
- Use SSL/TLS for database connections in production

### 3. Access Control
```bash
# Restrict PostgreSQL access to specific users/IPs in pg_hba.conf
# Restrict Redis to specific networks
# Configure Prefect API authentication tokens
```

---

## Troubleshooting

### PostgreSQL Connection Issues
```bash
# Check if service is running
docker-compose ps postgresql

# View logs
docker-compose logs postgresql

# Test connection
docker-compose exec postgresql pg_isready -U metadata_user -d financial_metadata
```

### MongoDB Connection Issues
```bash
# View logs
docker-compose logs mongodb

# Test connection
docker-compose exec mongodb mongosh --username admin --password admin --authenticationDatabase admin
```

### Memory Issues
```bash
# Check resource usage
docker stats

# Increase Docker memory limit in .env
METADATA_POSTGRES_MEMORY=512   # Increase to 512MB
```

### Port Conflicts
If ports are already in use, modify the external ports in `.env`:
```bash
PF_POSTGRES_EXTERNAL_PORT=5435
METADATA_POSTGRES_EXTERNAL_PORT=5435
```

---

## Additional Resources

- **Prefect Documentation**: https://docs.prefect.io/
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/17/
- **MongoDB Documentation**: https://docs.mongodb.com/
- **MLflow Documentation**: https://mlflow.org/docs/latest/
- **Redis Documentation**: https://redis.io/documentation

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs <service-name>`
2. Review `.env` configuration
3. Verify network connectivity: `docker network inspect <network-name>`
4. Consult service-specific documentation

---

**Last Updated**: 2026-05-28  
**Version**: 1.0
