# Environment Configuration Guide

## Overview

This guide explains how to configure and manage environment variables for the Financial News RAG Stack. All sensitive information and configuration parameters should be stored in the `.env` file, never hardcoded into the application.

---

## Files Structure

```
financial-news/
├── .env                              # Actual configuration (DO NOT commit!)
├── .env.example                      # Template with documentation (commit this)
├── docker-compose.yml                # Service definitions
├── ENVIRONMENT_SETUP.md              # Detailed setup guide
└── docker/postgresql/
    ├── Dockerfile                    # PostgreSQL 17 metadata container
    └── init-scripts/
        ├── 001-create-schema.sql     # Schema and tables creation
        └── 002-create-utilities.sql  # Views and utility functions
```

---

## Quick Start

### 1. Create `.env` from Template
```bash
cp .env.example .env
```

### 2. Review Default Values
The `.env` file comes pre-populated with development values. Edit as needed:
```bash
# Edit with your preferred editor
nano .env
# or
vi .env
```

### 3. Start Services
```bash
docker-compose up -d
```

---

## Environment Variables by Service

### General Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `APP_ENV` | development | Environment type | `development`, `staging`, `production` |
| `APP_NAME` | financial-news-rag | Application identifier | `financial-news-rag` |
| `LOG_LEVEL` | INFO | Log verbosity | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### MongoDB Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `MONGO_USER` | admin | Root username | `admin` |
| `MONGO_PASSWORD` | admin | Root password | `secure-password-123` |
| `MONGO_PORT` | 27017 | Internal port | `27017` |
| `MONGO_DB_RAW` | financial_news_raw | Raw articles database | `financial_news_raw` |
| `MONGO_DB_PROCESSED` | financial_news_processed | Processed articles database | `financial_news_processed` |

### PostgreSQL - Prefect (Orchestration Database)

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `PF_POSTGRES_USER` | prefect | Database user | `prefect` |
| `PF_POSTGRES_PASSWORD` | prefect | Database password | `prefect-password` |
| `PF_POSTGRES_DB` | prefectdb | Database name | `prefectdb` |
| `PF_POSTGRES_INTERNAL_PORT` | 5432 | Internal port | `5432` |
| `PF_POSTGRES_EXTERNAL_PORT` | 5432 | External/host port | `5432` |
| `PF_POSTGRES_HOST` | posgresql-prefect | Service hostname | `posgresql-prefect` |

### PostgreSQL - Metadata Storage (NEW)

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `METADATA_POSTGRES_USER` | metadata_user | Database user | `metadata_user` |
| `METADATA_POSTGRES_PASSWORD` | metadata_password | Database password | `metadata_password` |
| `METADATA_POSTGRES_DB` | financial_metadata | Database name | `financial_metadata` |
| `METADATA_POSTGRES_INTERNAL_PORT` | 5432 | Internal port | `5432` |
| `METADATA_POSTGRES_EXTERNAL_PORT` | 5434 | External/host port | `5434` |
| `METADATA_POSTGRES_HOST` | postgresql | Service hostname | `postgresql` |
| `METADATA_POSTGRES_SHARED_BUFFERS` | 64MB | Memory for caching | `256MB`, `4GB` |
| `METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE` | 256MB | Total cache size | `1GB`, `32GB` |
| `METADATA_POSTGRES_WORK_MEM` | 4MB | Per-operation memory | `16MB`, `64MB` |
| `METADATA_POSTGRES_MAINTENANCE_WORK_MEM` | 64MB | Maintenance memory | `256MB`, `512MB` |
| `METADATA_POSTGRES_MAX_CONNECTIONS` | 100 | Max connections | `50`, `200`, `500` |

### Redis Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `REDIS_HOST` | redis-prefect | Service hostname | `redis-prefect` |
| `REDIS_PORT` | 6379 | Port | `6379` |
| `REDIS_MESSAGING_DB` | 0 | Messaging database index | `0` |
| `REDIS_CACHE_DB` | 1 | Cache database index | `1` |
| `REDIS_PASSWORD` | (empty) | Password | `redis-password` |

### MLflow Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `MLFLOW_HOST` | mlflow | Service hostname | `mlflow` |
| `MLFLOW_PORT` | 5000 | Port | `5000` |
| `MLFLOW_ARTIFACT_PATH` | /mlflow/artifacts | Artifact storage | `/mlflow/artifacts` |
| `MLFLOW_BACKEND_STORE` | /mlflow/store | Backend storage | `/mlflow/store` |
| `MLFLOW_TRACKING_URI` | http://mlflow:5000 | Tracking URI | `http://mlflow:5000` |

### Prefect Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `PREFECT_SERVER_HOST` | prefect-server | Server hostname | `prefect-server` |
| `PREFECT_SERVER_PORT` | 4200 | Server port | `4200` |
| `PREFECT_API_URL` | http://prefect-server:4200/api | API endpoint | `http://prefect-server:4200/api` |
| `PREFECT_SQLALCHEMY_POOL_SIZE` | 20 | Connection pool size | `20`, `50` |
| `PREFECT_SQLALCHEMY_MAX_OVERFLOW` | 10 | Max overflow connections | `10`, `20` |
| `PREFECT_RUNS_RETENTION_DAYS` | 30 | Retention period | `7`, `30`, `90` |
| `PREFECT_LOGGING_LEVEL` | INFO | Log level | `DEBUG`, `INFO`, `WARNING` |

### Data Ingestion Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `SCRAPER_TIMEOUT` | 30 | Request timeout (seconds) | `30`, `60` |
| `SCRAPER_MAX_RETRIES` | 3 | Retry attempts | `3`, `5` |
| `SCRAPER_DELAY` | 1 | Delay between requests (seconds) | `1`, `5` |
| `CONTENT_STORAGE_BACKEND` | adls | Article content backend: `adls` for production, `minio` for local-only testing | `adls`, `minio` |
| `MINIO_ENDPOINT` | localhost:9000 | MinIO endpoint for host-side local scraper tests | `localhost:9000` |
| `MINIO_BUCKET` | financialnews-datalake | Local MinIO bucket mirroring the ADLS filesystem/container name | `financialnews-datalake` |
| `INGESTION_BATCH_SIZE` | 100 | Batch processing size | `50`, `100`, `500` |
| `INGESTION_WORKERS` | 4 | Worker threads | `2`, `4`, `8` |
| `INGESTION_LOG_DIR` | ./logs/ingestion | Log directory | `./logs/ingestion` |

### Docker Network & Volumes

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `DOCKER_NETWORK` | financial-net | Primary network | `financial-net` |
| `MONGO_NETWORK` | vifinner-net | MongoDB network | `vifinner-net` |
| `POSTGRES_DATA_VOLUME` | postgres_data | Prefect PG volume | `postgres_data` |
| `METADATA_POSTGRES_DATA_VOLUME` | metadata_postgres_data | Metadata PG volume | `metadata_postgres_data` |
| `REDIS_DATA_VOLUME` | redis_data | Redis volume | `redis_data` |
| `MLFLOW_STORE_VOLUME` | mlflow_store | MLflow store | `mlflow_store` |
| `MLFLOW_ARTIFACTS_VOLUME` | mlflow_artifacts | MLflow artifacts | `mlflow_artifacts` |

### Container Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `CONTAINER_RESTART_POLICY` | unless-stopped | Restart policy | `unless-stopped`, `always` |
| `HEALTH_CHECK_INTERVAL` | 10 | Check interval (seconds) | `10`, `30` |
| `HEALTH_CHECK_TIMEOUT` | 5 | Check timeout (seconds) | `5`, `10` |
| `HEALTH_CHECK_RETRIES` | 5 | Retry attempts | `3`, `5` |
| `HEALTH_CHECK_START_PERIOD` | 10 | Start period (seconds) | `10`, `30` |

### Security Configuration

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `POSTGRES_SSL_ENABLED` | false | Enable SSL | `true`, `false` |
| `POSTGRES_SSL_MODE` | disable | SSL mode | `disable`, `require`, `verify-full` |
| `JWT_SECRET_KEY` | dev-secret-key-not-for-production | JWT secret | Generate with `openssl rand -base64 32` |
| `API_TOKEN` | dev-api-token-not-for-production | API token | Generate with `openssl rand -base64 32` |

### Monitoring & Debugging

| Variable | Default | Description | Example |
|----------|---------|-------------|---------|
| `DEBUG` | false | Debug mode | `true`, `false` |
| `PROMETHEUS_ENABLED` | false | Enable metrics | `true`, `false` |
| `PROMETHEUS_PORT` | 9090 | Metrics port | `9090` |
| `LOG_REQUESTS` | false | Log HTTP requests | `true`, `false` |
| `LOG_SQL_QUERIES` | false | Log SQL queries | `true`, `false` |

---

## Configuration Profiles

### Development Configuration
```bash
APP_ENV=development
LOG_LEVEL=DEBUG
DEBUG=true
METADATA_POSTGRES_SHARED_BUFFERS=32MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=128MB
METADATA_POSTGRES_MAX_CONNECTIONS=50
PREFECT_LOGGING_LEVEL=DEBUG
LOG_REQUESTS=true
LOG_SQL_QUERIES=true
```

### Staging Configuration
```bash
APP_ENV=staging
LOG_LEVEL=INFO
DEBUG=false
METADATA_POSTGRES_SHARED_BUFFERS=256MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
METADATA_POSTGRES_MAX_CONNECTIONS=100
PREFECT_LOGGING_LEVEL=INFO
POSTGRES_SSL_MODE=prefer
```

### Production Configuration
```bash
APP_ENV=production
LOG_LEVEL=WARNING
DEBUG=false
METADATA_POSTGRES_SHARED_BUFFERS=4GB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=16GB
METADATA_POSTGRES_MAX_CONNECTIONS=500
PREFECT_LOGGING_LEVEL=WARNING
POSTGRES_SSL_MODE=require
CONTAINER_RESTART_POLICY=always
# Change default passwords!
MONGO_PASSWORD=<strong-password>
PF_POSTGRES_PASSWORD=<strong-password>
METADATA_POSTGRES_PASSWORD=<strong-password>
JWT_SECRET_KEY=<generate-new-key>
API_TOKEN=<generate-new-token>
```

---

## PostgreSQL 17 Performance Tuning

The PostgreSQL 17 metadata database requires careful performance tuning based on workload:

### Low Traffic (< 100 concurrent users)
```bash
METADATA_POSTGRES_SHARED_BUFFERS=64MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=256MB
METADATA_POSTGRES_WORK_MEM=4MB
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=64MB
METADATA_POSTGRES_MAX_CONNECTIONS=50
```

### Medium Traffic (100-1000 concurrent users)
```bash
METADATA_POSTGRES_SHARED_BUFFERS=512MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=2GB
METADATA_POSTGRES_WORK_MEM=16MB
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=256MB
METADATA_POSTGRES_MAX_CONNECTIONS=200
```

### High Traffic (> 1000 concurrent users)
```bash
METADATA_POSTGRES_SHARED_BUFFERS=8GB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=32GB
METADATA_POSTGRES_WORK_MEM=64MB
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=512MB
METADATA_POSTGRES_MAX_CONNECTIONS=500
```

---

## Security Best Practices

### 1. Password Generation
```bash
# Generate strong passwords
openssl rand -base64 32
# Output: XXXXXXXXXXXXXXXXXXXXXXXXXXXXX=

# Update in .env
MONGO_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXX=
PF_POSTGRES_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXX=
METADATA_POSTGRES_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXX=
```

### 2. Secret Management
Never commit `.env` to version control:
```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore
echo ".env.production" >> .gitignore
```

### 3. Environment Variable Injection
```bash
# Method 1: Load from file
export $(cat .env | grep -v '^#' | xargs)

# Method 2: Use env-files with Docker
docker-compose --env-file .env.production up -d

# Method 3: Using secrets (Docker Swarm)
docker secret create db_password <(echo 'password123')
```

### 4. Sensitive Values in CI/CD
For GitHub Actions:
```yaml
env:
  METADATA_POSTGRES_PASSWORD: ${{ secrets.DB_PASSWORD }}
  JWT_SECRET_KEY: ${{ secrets.JWT_KEY }}
  API_TOKEN: ${{ secrets.API_TOKEN }}
```

---

## Validation & Testing

### Validate Configuration
```bash
# Check if all required variables are set
grep "=" .env | wc -l

# Verify PostgreSQL credentials
psql -h localhost -p 5434 -U metadata_user -d financial_metadata -c "SELECT version();"

# Verify Redis connection
redis-cli -h localhost -p 6379 PING

# Verify MongoDB
mongosh mongodb://admin:admin@localhost:27017/admin
```

### Test Docker Compose
```bash
# Validate syntax
docker-compose config

# Start services
docker-compose up -d

# Check health
docker-compose ps
```

---

## Troubleshooting

### Service Won't Start
1. Check environment variables: `docker-compose config`
2. View logs: `docker-compose logs <service>`
3. Verify ports aren't in use: `lsof -i :<port>`

### Connection Refused
1. Check service is running: `docker-compose ps`
2. Verify environment variables point to correct host
3. Check network connectivity: `docker network inspect <network>`

### Performance Issues
1. Review PostgreSQL configuration in `.env`
2. Check `METADATA_POSTGRES_SHARED_BUFFERS` and `METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE`
3. Increase `METADATA_POSTGRES_MAX_CONNECTIONS` if needed

---

## Migration & Updates

### Updating Environment Variables
1. Backup current `.env`: `cp .env .env.backup`
2. Compare with `.env.example`: `diff .env .env.example`
3. Update `.env` with new variables
4. Restart services: `docker-compose restart`

### Scaling Resources
To increase PostgreSQL resource allocation:
```bash
# Update .env
METADATA_POSTGRES_SHARED_BUFFERS=2GB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=8GB

# Restart service
docker-compose restart postgresql
```

---

## Reference Documentation

- **PostgreSQL**: https://www.postgresql.org/docs/17/
- **MongoDB**: https://docs.mongodb.com/
- **Docker Compose**: https://docs.docker.com/compose/
- **Prefect**: https://docs.prefect.io/

---

**Last Updated**: 2026-05-28  
**Version**: 1.0
