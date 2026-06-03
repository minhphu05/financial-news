# Runbook — Operations Guide

Day-to-day operations: starting services, running the scraper, debugging problems, and maintaining the stack.

---

## Quick Start (From Scratch)

```bash
# 1. Clone & configure
cp .env.example .env
# Edit .env — at minimum verify MONGO_PASSWORD, METADATA_POSTGRES_PASSWORD

# 2. Create required host directories
mkdir -p logs/scraper

# 3. Pull images and start all services
docker-compose pull
docker-compose up -d

# 4. Verify everything is healthy
docker-compose ps

# 5. Open Grafana
open http://localhost:3000          # admin / admin

# 6. Run the scraper manually
python -m src.scraper.run --ticker BCM --max-pages 2 --triggered-by manual

# 7. Watch logs in Grafana
# Go to http://localhost:3000 → Explore → Loki → {job="scraper"}
```

---

## Service Management

### Start / Stop / Restart

```bash
# Start all services (detached)
docker-compose up -d

# Stop all services (preserves data volumes)
docker-compose down

# Stop and remove everything including volumes (DESTRUCTIVE — dev only)
docker-compose down -v

# Restart a single service
docker-compose restart financial-loki
docker-compose restart financial-grafana
docker-compose restart financial-fluent-bit

# Rebuild the worker image (after code changes)
docker-compose build financial-pf-worker
docker-compose up -d financial-pf-worker
```

### Check Service Health

```bash
# Summary of all containers (status, ports, health)
docker-compose ps

# Tailing logs for specific services
docker-compose logs -f financial-fluent-bit
docker-compose logs -f financial-loki
docker-compose logs -f financial-prometheus

# Check all service health at once
for svc in financial-loki financial-grafana financial-prometheus financial-pushgateway; do
    echo -n "$svc: "
    docker inspect --format='{{.State.Health.Status}}' $svc 2>/dev/null || echo "no healthcheck"
done
```

### Endpoint Health Checks

```bash
# Loki
curl http://localhost:3100/ready

# Prometheus
curl http://localhost:9090/-/healthy

# Pushgateway
curl http://localhost:9091/-/healthy

# Prefect
curl http://localhost:4200/api/health

# Fluent Bit metrics
curl http://localhost:2020/metrics | head -20
```

---

## Running the Scraper

### Common Invocations

```bash
# All tickers — standard daily run
python -m src.scraper.run --triggered-by cron

# Single ticker — for testing or backfill
python -m src.scraper.run --ticker BCM --triggered-by manual

# Multiple tickers
python -m src.scraper.run --ticker ACB --ticker BID --triggered-by manual

# Limit pages (useful for smoke tests)
python -m src.scraper.run --ticker BCM --max-pages 3 --triggered-by manual

# Override threshold — more aggressive early-stop for a quick refresh
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=3 python -m src.scraper.run --triggered-by cron

# Full archive backfill — disable early-stop
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=9999 CAFEF_MAX_PAGES=200 \
  python -m src.scraper.run --triggered-by manual
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--ticker` | (all) | Ticker symbol(s) to filter; repeatable |
| `--max-pages` | from `.env` | Override max listing pages |
| `--triggered-by` | `manual` | One of `manual`, `cron`, `prefect` |

### Checking Output

```bash
# View the latest log file
ls -t logs/scraper/*.log | head -1 | xargs tail -f

# View the latest JSON log (structured)
ls -t logs/scraper/*.json.log | head -1 | xargs cat | python -m json.tool | head -50
```

---

## Database Operations

### PostgreSQL — Metadata

```bash
# Connect
psql -h localhost -p 5434 -U metadata_user -d financial_metadata

# Quick stats
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "SELECT ticker_symbol, COUNT(*) FROM news_articles GROUP BY 1 ORDER BY 1;"

# Recent scrape runs
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "SELECT run_id, started_at, duration_seconds, articles_new, status FROM scrape_runs ORDER BY started_at DESC LIMIT 5;"

# Scrape progress
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "SELECT ticker_symbol, keyword, last_page_scraped, total_articles_scraped, is_exhausted FROM scrape_progress ORDER BY 1, 2;"
```

### MongoDB — Content

```bash
# Connect
mongosh "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin"

# Article count
mongosh --quiet "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin" \
  --eval "db.articles_content.countDocuments()"

# Count by ticker
mongosh --quiet "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin" \
  --eval "db.articles_content.aggregate([{'\$group':{_id:'\$ticker_symbol',count:{'\$sum':1}}}]).toArray()"
```

### Backup

```bash
# PostgreSQL backup
pg_dump -h localhost -p 5434 -U metadata_user financial_metadata \
  > backups/financial_metadata_$(date +%Y%m%d).sql

# MongoDB backup
mongodump \
  --uri "mongodb://admin:admin@localhost:27018/?authSource=admin" \
  --db financial_news_raw \
  --out backups/mongo_$(date +%Y%m%d)/

# Restore PostgreSQL
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  < backups/financial_metadata_20260528.sql

# Restore MongoDB
mongorestore \
  --uri "mongodb://admin:admin@localhost:27018/?authSource=admin" \
  --db financial_news_raw \
  backups/mongo_20260528/financial_news_raw/
```

---

## Grafana Operations

### Dashboard Management

```bash
# Grafana provisioning config location
ls docker/grafana/provisioning/

# To add a new dashboard:
# 1. Build it in Grafana UI → Export → Save JSON
# 2. Copy JSON to: docker/grafana/provisioning/dashboards/json/my-dashboard.json
# 3. Restart Grafana to load it (or wait for auto-refresh)
docker-compose restart financial-grafana
```

### Reset Grafana to Factory State

```bash
# Stop Grafana and remove its data volume
docker-compose stop financial-grafana
docker volume rm financial-news_grafana_data

# Restart — provisioned datasources/dashboards will be re-applied
docker-compose up -d financial-grafana
```

### Export Current Dashboards

```bash
# Via Grafana API (replace DASHBOARD_UID)
curl -s http://admin:admin@localhost:3000/api/dashboards/uid/scraper-overview \
  | python -m json.tool > docker/grafana/provisioning/dashboards/json/scraper-overview.json
```

---

## Loki Operations

### Querying Logs (CLI)

```bash
# Install logcli (Loki's command-line client)
brew install logcli                    # macOS
# or download: https://github.com/grafana/loki/releases

# Set endpoint
export LOKI_ADDR=http://localhost:3100

# Recent errors
logcli query '{job="scraper", level="ERROR"}' --limit=50 --since=24h

# Watch live logs (tail)
logcli query '{job="scraper"}' --tail

# Count lines per ticker (last hour)
logcli query 'sum by (ticker_symbol) (count_over_time({job="scraper"}[1h]))' --stats
```

### Retention and Disk Usage

```bash
# Check Loki data volume size
docker system df -v | grep loki

# Loki config controls retention (currently 7 days reject window)
# To change retention, edit docker/loki/loki-config.yaml:
#   limits_config:
#     reject_old_samples_max_age: 168h   # 7 days

# Restart after config change
docker-compose restart financial-loki
```

---

## Prefect Operations

### Worker Status

```bash
# Check worker logs
docker-compose logs -f financial-pf-worker

# Verify the worker is registered
curl -s http://localhost:4200/api/work-pools/ | python -m json.tool

# Restart worker
docker-compose restart financial-pf-worker
```

### Deploying a Flow

```bash
# Inside the worker container
docker exec -it financial-pf-worker bash

# Or on host machine (with Prefect installed)
export PREFECT_API_URL=http://localhost:4200/api
python -m src.flows.deploy   # adjust to your actual deploy script
```

---

## Troubleshooting Playbook

### Problem: Scraper exits immediately with no articles

```bash
# Check connectivity to CafeF (may be blocked or down)
curl -s "https://cafef.vn/tim-kiem/trang-1.chn?keywords=BCM" | head -100

# Check PostgreSQL connectivity
python -c "
from src.scraper.config import get_settings
from src.scraper.storage import StorageManager
s = get_settings()
with StorageManager(s) as st:
    print('DB ok, article count:', st.count_articles())
"

# Check MongoDB connectivity
mongosh "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin" \
  --eval "db.runCommand({ping:1})"
```

### Problem: Fluent Bit not shipping logs to Loki

```bash
# 1. Check Fluent Bit is running
docker-compose ps financial-fluent-bit

# 2. View Fluent Bit logs for errors
docker-compose logs --tail=50 financial-fluent-bit

# 3. Verify the log file exists and has content
ls -la logs/scraper/
cat logs/scraper/*.json.log | head -5

# 4. Validate JSON format (must be valid JSON per line)
cat logs/scraper/*.json.log | python -c "import sys,json; [json.loads(l) for l in sys.stdin]"
echo "JSON valid: $?"

# 5. Test Loki reachability from within Fluent Bit container
docker exec financial-fluent-bit wget -qO- http://loki:3100/ready

# 6. Check Fluent Bit output metrics
curl http://localhost:2020/metrics | grep output
```

### Problem: Loki returns no logs in Grafana

```bash
# 1. Confirm Loki has data
curl -G http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={job="scraper"}' \
  --data-urlencode 'limit=5'

# 2. Check Loki labels exist
curl http://localhost:3100/loki/api/v1/labels

# 3. Verify Grafana can reach Loki
docker exec financial-grafana wget -qO- http://loki:3100/ready

# 4. In Grafana, check datasource: Settings → Data Sources → Loki → Test
# 5. Check time range in Grafana — is it set to the right window?
```

### Problem: `scrape_runs` row stuck in `status='running'`

```bash
# Find zombie runs
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "SELECT run_id, started_at FROM scrape_runs WHERE status = 'running';"

# Mark as aborted
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "UPDATE scrape_runs SET status='aborted', finished_at=NOW() WHERE status='running';"
```

### Problem: PostgreSQL table doesn't exist

```bash
# The tables are created automatically by StorageManager.__enter__
# Trigger creation by doing a minimal dry run:
python -c "
from src.scraper.config import get_settings
from src.scraper.storage import StorageManager
with StorageManager(get_settings()) as s:
    print('Tables exist:', s.article_exists('0'))
"

# List existing tables
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "\dt"
```

### Problem: Out of disk space on Docker

```bash
# See Docker disk usage
docker system df

# Remove dangling images and stopped containers
docker system prune -f

# Remove unused volumes (CAREFUL — verify which volumes are safe to remove)
docker volume ls
docker volume prune -f     # removes all volumes not used by any container

# Remove specific old log files
find logs/scraper/ -name "*.log" -mtime +30 -delete
```

---

## Maintenance Tasks

### Rotate Old Log Files (Monthly)

```bash
# Remove JSON logs older than 30 days
find logs/scraper/ -name "*.json.log" -mtime +30 -delete

# Remove plain text logs older than 60 days
find logs/scraper/ -name "*.log" -not -name "*.json.log" -mtime +60 -delete
```

### Vacuum PostgreSQL

```bash
psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "VACUUM ANALYZE news_articles;"

psql -h localhost -p 5434 -U metadata_user -d financial_metadata \
  -c "VACUUM ANALYZE scrape_runs;"
```

### Update Docker Images

```bash
# Pull latest versions of all images
docker-compose pull

# Recreate containers with new images
docker-compose up -d --force-recreate

# Verify no containers are still using old images
docker image prune -f
```

---

## Useful Aliases (Add to ~/.zshrc)

```bash
alias fn-up='cd ~/Documents/Project/financial-news && docker-compose up -d'
alias fn-down='cd ~/Documents/Project/financial-news && docker-compose down'
alias fn-logs='cd ~/Documents/Project/financial-news && docker-compose logs -f'
alias fn-ps='cd ~/Documents/Project/financial-news && docker-compose ps'
alias fn-scrape='cd ~/Documents/Project/financial-news && python -m src.scraper.run'
alias fn-grafana='open http://localhost:3000'
alias fn-prefect='open http://localhost:4200'
alias fn-psql='psql -h localhost -p 5434 -U metadata_user -d financial_metadata'
alias fn-mongo='mongosh "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin"'
```
</content>
