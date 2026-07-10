# Fluent Bit

Fluent Bit tail JSON logs tu scraper/pipeline va day vao Loki.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d fluent-bit loki
```

Metrics endpoint:

- http://localhost:2020/api/v1/metrics/prometheus

Config:

- `docker/fluent-bit/fluent-bit.conf`
- `docker/fluent-bit/parsers.conf`

## Log paths dang duoc tail

Container path:

```text
/var/log/scraper/*.json.log
/var/log/pipeline/chunk.json.log
/var/log/pipeline/embed.json.log
/var/log/pipeline/upsert.json.log
/var/log/pipeline/clean.json.log
/var/log/pipeline/scrape.json.log
/var/log/pipeline/pipeline.json.log
```

Host path tuong ung:

```text
logs/scraper/*.json.log
logs/pipeline/*.json.log
```

## Them log source moi

1. Dam bao app ghi JSON line, moi line la mot object JSON co `timestamp`, `level`, `message`.
2. Them input vao `fluent-bit.conf`:

```ini
[INPUT]
    Name              tail
    Tag               my-stage.*
    Path              /var/log/my-stage/*.json.log
    Parser            json
    Refresh_Interval  1
    Rotate_Wait       30
    Skip_Long_Lines   On
    Read_from_Head    Off
    DB                /var/log/flb_my_stage.db
```

3. Them filter label bo sung neu can:

```ini
[FILTER]
    Name   record_modifier
    Match  my-stage.*
    Record service my-stage
```

4. Them output Loki:

```ini
[OUTPUT]
    Name        loki
    Match       my-stage.*
    Host        loki
    Port        3100
    Labels      job=my-stage, service=my-stage
    Label_Keys  $level,$stage,$run_id
    Line_Format json
```

5. Mount folder log vao service `fluent-bit` trong compose.

## Label strategy

Nen dung label cardinality thap:

- `job`
- `service`
- `level`
- `stage`
- `source_name`
- `ticker_symbol` neu can filter theo ticker

Khong nen dung label cho URL, title, raw message, exception text.

## Kiem tra Fluent Bit

```powershell
Invoke-RestMethod http://localhost:2020/api/v1/metrics/prometheus
```

PromQL:

```promql
sum(rate(fluentbit_input_records_total[1m]))
sum(rate(fluentbit_output_proc_records_total[1m]))
sum(rate(fluentbit_output_errors_total[5m]))
```

LogQL:

```logql
{job="scraper"}
{job="ingestion-pipeline"}
```

## Troubleshooting

- Khong co logs trong Loki: kiem tra file co duoc ghi vao `logs/...` khong.
- `fluentbit_output_errors_total` tang: Loki down, sai host/port, hoac label config invalid.
- Logs cu khong duoc doc lai: `Read_from_Head Off` va DB offset da ghi. Xoa DB file trong container/volume neu muon doc lai tu dau.
