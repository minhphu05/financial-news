# Quick Reference - Environment Variables

## Essential Commands

```bash
# Setup
cp .env.example .env
nano .env                          # Edit configuration

# Services
docker-compose up -d               # Start all services
docker-compose down                # Stop all services
docker-compose restart             # Restart services
docker-compose logs -f             # View logs
docker-compose ps                  # Check status

# Database
psql -h localhost -p 5434 -U metadata_user -d financial_metadata
mongo mongodb://admin:admin@localhost:27017/admin
redis-cli -h localhost -p 6379 PING

# Access Services
Prefect UI:    http://localhost:4200
MLflow UI:     http://localhost:5000
```

---

## Critical Environment Variables

### Database Credentials
```
MONGO_USER=admin
MONGO_PASSWORD=admin

PF_POSTGRES_USER=prefect
PF_POSTGRES_PASSWORD=prefect

METADATA_POSTGRES_USER=metadata_user
METADATA_POSTGRES_PASSWORD=metadata_password
```

### Database Ports
```
MongoDB:              27017 → 27018
PostgreSQL (Prefect): 5432 → 5432
PostgreSQL (Metadata):5432 → 5434
Redis:                6379 → 6379
Prefect Server:       4200 → 4200
MLflow:               5000 → 5000
```

### PostgreSQL 17 Performance
```
METADATA_POSTGRES_SHARED_BUFFERS=64MB
METADATA_POSTGRES_EFFECTIVE_CACHE_SIZE=256MB
METADATA_POSTGRES_WORK_MEM=4MB
METADATA_POSTGRES_MAINTENANCE_WORK_MEM=64MB
METADATA_POSTGRES_MAX_CONNECTIONS=100
```

---

## Environments

### Development
```
APP_ENV=development
LOG_LEVEL=DEBUG
DEBUG=true
```

### Production
```
APP_ENV=production
LOG_LEVEL=WARNING
DEBUG=false
POSTGRES_SSL_MODE=require
# Change all default passwords!
```

---

## Database Schema

PostgreSQL 17 tables (auto-created):
- `articles` - Article metadata
- `embeddings` - Vector embeddings
- `ner_labels` - Named entity labels
- `extraction_spans` - Extracted text spans
- `processing_events` - Processing history
- `datasets` - Dataset definitions
- `user_activity` - User interactions

---

## Useful Views

```sql
SELECT * FROM articles_processing_summary;
SELECT * FROM embedding_coverage;
SELECT * FROM ner_statistics;
SELECT * FROM articles_without_embeddings;

-- Custom functions
SELECT * FROM get_dataset_statistics('dataset_name');
SELECT * FROM get_article_processing_timeline(article_id);
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Port already in use | Change external port in .env |
| PostgreSQL won't connect | Check credentials in .env |
| Out of memory | Increase Docker memory limit |
| Services not starting | Check `.env` syntax, run `docker-compose config` |
| Database reset needed | Remove volume: `docker volume rm <vol>` |

---

## Security Reminders

✅ DO:
- Use strong passwords in production
- Keep `.env` out of version control
- Rotate secrets regularly
- Use SSL in production
- Monitor access logs

❌ DON'T:
- Hardcode sensitive values
- Share `.env` files
- Use default passwords
- Disable health checks
- Expose ports unnecessarily

---

## File Locations

```
.env                           # Configuration (DO NOT commit!)
.env.example                   # Template (commit this)
ENVIRONMENT_SETUP.md           # Detailed guide
ENV_GUIDE.md                   # This reference
docker/postgresql/Dockerfile   # PostgreSQL 17 definition
docker/postgresql/init-scripts/001-create-schema.sql
docker/postgresql/init-scripts/002-create-utilities.sql
```

---

**Version**: 1.0 | **Updated**: 2026-05-28
